"""GPU Worker — polls the Cloudflare Queue and processes video jobs.

Responsibilities:
  1. Long-poll the video-processing-jobs queue via the Cloudflare Queues HTTP API.
  2. Download the source video from R2.
  3. Run the requested processing stage (ingest | segment | calibrate | detect |
     track | reid | events | labels | metrics | render).
  4. Upload results back to R2 and update the job status in the database.

Environment variables (all required unless noted):
  CLOUDFLARE_ACCOUNT_ID     — Cloudflare account ID
  CLOUDFLARE_API_TOKEN      — Cloudflare API token with Queues read permission
  CF_QUEUE_VIDEO_PROCESSING — queue name (default: video-processing-jobs)
  R2_ACCESS_KEY_ID          — R2 S3-compat access key
  R2_SECRET_ACCESS_KEY      — R2 S3-compat secret key
  R2_ENDPOINT_URL           — R2 S3-compat endpoint
  R2_BUCKET_NAME            — R2 bucket (default: football-iq)
  GPU_WORKER_POLL_INTERVAL  — seconds between queue polls (default: 10)
  BACKEND_API_URL           — backend base URL for job status callbacks
  MODEL_DETECT_PATH         — path to YOLO weights (default: yolov8n.pt)
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Any

import httpx
import structlog

# ── Logging setup ─────────────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logging.basicConfig(level=logging.INFO)
log = structlog.get_logger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
ACCOUNT_ID = os.environ["CLOUDFLARE_ACCOUNT_ID"]
API_TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
QUEUE_NAME = os.environ.get("CF_QUEUE_VIDEO_PROCESSING", "video-processing-jobs")
POLL_INTERVAL = int(os.environ.get("GPU_WORKER_POLL_INTERVAL", "10"))
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "")

CF_QUEUES_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
    f"/queues/{QUEUE_NAME}/messages/pull"
)

# ── Graceful shutdown ─────────────────────────────────────────────────────────
_shutdown = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown
    log.info("shutdown_signal_received", signal=signum)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ── Queue polling ─────────────────────────────────────────────────────────────

def pull_messages(client: httpx.Client, batch_size: int = 5) -> list[dict[str, Any]]:
    """Pull up to `batch_size` messages from the Cloudflare Queue."""
    resp = client.post(
        CF_QUEUES_URL,
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        json={"batch_size": batch_size, "visibility_timeout_ms": 60_000},
        timeout=30,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data.get("result", {}).get("messages", [])


def ack_message(client: httpx.Client, lease_id: str) -> None:
    """Acknowledge (delete) a processed message from the queue."""
    ack_url = (
        f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
        f"/queues/{QUEUE_NAME}/messages/ack"
    )
    resp = client.post(
        ack_url,
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        json={"acks": [{"lease_id": lease_id}]},
        timeout=15,
    )
    resp.raise_for_status()


# ── Job processing ────────────────────────────────────────────────────────────

def process_job(job: dict[str, Any]) -> None:
    """Dispatch a single job to the appropriate processing stage."""
    job_id: str = job.get("jobId", "unknown")
    job_type: str = job.get("jobType", "")
    video_id: str = job.get("videoId", "")
    clip_id: str = job.get("clipId", "")
    input_uri: str = job.get("inputUri", "")
    # Artifacts passed in from a preceding stage (e.g. detections for track stage)
    input_artifacts: dict[str, Any] = job.get("inputArtifacts", {})

    log.info("processing_job", job_id=job_id, job_type=job_type,
             video_id=video_id, clip_id=clip_id)

    _update_job_status(job_id, "running")

    try:
        artifacts = _dispatch(job_type, video_id, clip_id, input_uri,
                              input_artifacts, job_id)
        _update_job_status(job_id, "succeeded", output_artifacts=artifacts)
        log.info("job_succeeded", job_id=job_id)
    except Exception as exc:
        log.error("job_failed", job_id=job_id, error=str(exc))
        _update_job_status(job_id, "failed", error_message=str(exc))


def _dispatch(
    job_type: str,
    video_id: str,
    clip_id: str,
    input_uri: str,
    input_artifacts: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Route to the correct pipeline stage module."""
    from pipeline import (
        stage_calibrate,
        stage_detect,
        stage_events,
        stage_ingest,
        stage_labels,
        stage_metrics,
        stage_reid,
        stage_render,
        stage_segment,
        stage_track,
        r2 as r2_mod,
    )

    if job_type == "ingest":
        return stage_ingest.run(video_id, input_uri, job_id)

    elif job_type == "segment":
        return stage_segment.run(video_id, input_uri, job_id)

    elif job_type == "calibrate":
        return stage_calibrate.run(video_id, input_uri, job_id)

    elif job_type == "detect":
        # Returns detections dict in output_artifacts
        return stage_detect.run(video_id, input_uri, job_id)

    elif job_type == "track":
        detections: dict[str, Any] = input_artifacts.get("detections", {})
        fps: float = float(input_artifacts.get("fps", 30))
        return stage_track.run(clip_id, detections, fps, job_id)

    elif job_type == "reid":
        tracklet_ids: list[str] = input_artifacts.get("tracklet_ids", [])
        tracklets: list[dict[str, Any]] = input_artifacts.get("tracklets", [])
        roster: list[dict[str, Any]] = input_artifacts.get("roster", [])
        video_path = r2_mod.download_to_temp(_uri_to_r2_key(input_uri))
        try:
            return stage_reid.run(
                clip_id, video_path, tracklet_ids, tracklets, roster, BACKEND_API_URL
            )
        finally:
            video_path.unlink(missing_ok=True)

    elif job_type == "events":
        detections = input_artifacts.get("detections", {})
        fps = float(input_artifacts.get("fps", 30))
        return stage_events.run(clip_id, detections, fps, job_id)

    elif job_type == "labels":
        tracklets = input_artifacts.get("tracklets", [])
        events_list: list[dict[str, Any]] = input_artifacts.get("events", [])
        fps = float(input_artifacts.get("fps", 30))
        return stage_labels.run(clip_id, tracklets, events_list, fps)

    elif job_type == "metrics":
        tracklets = input_artifacts.get("tracklets", [])
        events_list = input_artifacts.get("events", [])
        analytics_safe: bool = bool(input_artifacts.get("analytics_safe", False))
        fps = float(input_artifacts.get("fps", 30))
        return stage_metrics.run(clip_id, tracklets, events_list,
                                 analytics_safe, fps, job_id)

    elif job_type == "pose":
        # Head-orientation estimation via RTMPose/ViTPose pose keypoints.
        # Derives per-frame head-yaw angles for QB progression reads,
        # LB/Safety play-action response, and CB technique analysis.
        # All metrics are written with experimental_flag=True and require
        # position-coach approval before surfacing in any staff view.
        # TODO: implement when model weights are available in R2.
        log.info("stage_pose_stub", video_id=video_id, clip_id=clip_id)
        return {}

    elif job_type == "render":
        tracklets = input_artifacts.get("tracklets", [])
        labels_list: list[dict[str, Any]] = input_artifacts.get("labels", [])
        metrics_list: list[dict[str, Any]] = input_artifacts.get("metrics", [])
        analytics_safe = bool(input_artifacts.get("analytics_safe", False))
        fps = float(input_artifacts.get("fps", 30))
        video_path = r2_mod.download_to_temp(_uri_to_r2_key(input_uri))
        try:
            return stage_render.run(
                clip_id, video_path, tracklets, labels_list, metrics_list,
                analytics_safe, fps, BACKEND_API_URL,
            )
        finally:
            video_path.unlink(missing_ok=True)

    else:
        log.warning("unknown_job_type", job_type=job_type, job_id=job_id)
        return {}


def _uri_to_r2_key(uri: str) -> str:
    if uri.startswith("r2://"):
        return "/".join(uri.split("/")[3:])
    return uri


def _update_job_status(
    job_id: str,
    status: str,
    error_message: str | None = None,
    output_artifacts: dict[str, Any] | None = None,
) -> None:
    if not BACKEND_API_URL:
        return
    try:
        payload: dict[str, Any] = {"status": status}
        if error_message:
            payload["error_message"] = error_message
        if output_artifacts:
            payload["output_artifacts"] = output_artifacts
        with httpx.Client(base_url=BACKEND_API_URL, timeout=10) as c:
            c.patch(f"/api/v1/jobs/{job_id}", json=payload)
    except Exception as exc:
        log.warning("status_update_failed", job_id=job_id, error=str(exc))


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("gpu_worker_starting", queue=QUEUE_NAME, poll_interval=POLL_INTERVAL)
    with httpx.Client() as client:
        while not _shutdown:
            try:
                messages = pull_messages(client)
                for msg in messages:
                    if _shutdown:
                        break
                    body: dict[str, Any] = msg.get("body", {})
                    lease_id: str = msg.get("lease_id", "")
                    process_job(body)
                    if lease_id:
                        ack_message(client, lease_id)

            except httpx.HTTPStatusError as exc:
                log.error("queue_pull_error", status=exc.response.status_code,
                          error=str(exc))
            except Exception as exc:
                log.error("worker_loop_error", error=str(exc))

            if not _shutdown:
                time.sleep(POLL_INTERVAL)

    log.info("gpu_worker_stopped")


if __name__ == "__main__":
    main()

