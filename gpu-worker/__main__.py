"""GPU Worker — polls the Cloudflare Queue and processes video jobs.

Responsibilities:
  1. Long-poll the video-processing-jobs queue via the Cloudflare Queues HTTP API.
  2. Download the source video from R2.
  3. Run the requested processing stage (ingest | segment | detect | track …).
  4. Upload results back to R2 and update the job status in the database.

Environment variables (all required unless noted):
  CLOUDFLARE_ACCOUNT_ID   — Cloudflare account ID
  CLOUDFLARE_API_TOKEN    — Cloudflare API token with Queues read permission
  CF_QUEUE_VIDEO_PROCESSING — queue name (default: video-processing-jobs)
  R2_ACCESS_KEY_ID        — R2 S3-compat access key
  R2_SECRET_ACCESS_KEY    — R2 S3-compat secret key
  R2_ENDPOINT_URL         — R2 S3-compat endpoint
  DATABASE_SYNC_URL       — postgres connection string for status updates
  GPU_WORKER_POLL_INTERVAL — seconds between queue polls (default: 10)
  BACKEND_API_URL         — backend base URL for job status callbacks
"""

from __future__ import annotations

import logging
import os
import signal
import time
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
    input_uri: str = job.get("inputUri", "")

    log.info("processing_job", job_id=job_id, job_type=job_type, video_id=video_id)

    # Update backend: job is now running
    _update_job_status(job_id, "running")

    try:
        if job_type == "ingest":
            _stage_ingest(video_id, input_uri)
        elif job_type == "segment":
            _stage_segment(video_id, input_uri)
        elif job_type == "detect":
            _stage_detect(video_id, input_uri)
        elif job_type == "track":
            _stage_track(video_id, input_uri)
        else:
            log.warning("unknown_job_type", job_type=job_type, job_id=job_id)

        _update_job_status(job_id, "succeeded")
        log.info("job_succeeded", job_id=job_id)
    except Exception as exc:
        log.error("job_failed", job_id=job_id, error=str(exc))
        _update_job_status(job_id, "failed", error_message=str(exc))


def _update_job_status(
    job_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    if not BACKEND_API_URL:
        return
    try:
        with httpx.Client(base_url=BACKEND_API_URL, timeout=10) as c:
            payload: dict[str, Any] = {"status": status}
            if error_message:
                payload["error_message"] = error_message
            c.patch(f"/api/v1/jobs/{job_id}", json=payload)
    except Exception as exc:
        log.warning("status_update_failed", job_id=job_id, error=str(exc))


# ── Processing stages (stubs — replace with real CV pipeline) ─────────────────

def _stage_ingest(video_id: str, input_uri: str) -> None:
    """Validate video metadata and store probed info."""
    log.info("stage_ingest", video_id=video_id, input_uri=input_uri)
    # TODO: probe with FFmpeg, validate codec/resolution/fps, generate thumbnail


def _stage_segment(video_id: str, input_uri: str) -> None:
    """Propose per-play clip boundaries."""
    log.info("stage_segment", video_id=video_id, input_uri=input_uri)
    # TODO: heuristic or model-based segmentation, write clips to DB + R2


def _stage_detect(video_id: str, input_uri: str) -> None:
    """Run YOLO player detection on each frame."""
    log.info("stage_detect", video_id=video_id, input_uri=input_uri)
    # TODO: load YOLO model, run inference, write bounding boxes


def _stage_track(video_id: str, input_uri: str) -> None:
    """Run ByteTrack / BoT-SORT player tracking."""
    log.info("stage_track", video_id=video_id, input_uri=input_uri)
    # TODO: run tracking, write tracklets to DB


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
                log.error("queue_pull_error", status=exc.response.status_code, error=str(exc))
            except Exception as exc:
                log.error("worker_loop_error", error=str(exc))

            if not _shutdown:
                time.sleep(POLL_INTERVAL)

    log.info("gpu_worker_stopped")


if __name__ == "__main__":
    main()
