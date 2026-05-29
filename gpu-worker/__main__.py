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
  MODEL_POSE_PATH           — path to RTMPose .pth weights (optional; stub used when absent)
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


def _add_service_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    event_dict.setdefault("service", "football-iq-gpu-worker")
    event_dict.setdefault("env", os.environ.get("ENVIRONMENT", "development"))
    return event_dict


structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_service_context,
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
    """Dispatch a single job to the appropriate processing stage.

    Same-session jobs (priority >= SAME_SESSION_PRIORITY) are wrapped in the
    8-minute timeout handler.  If the job exceeds the deadline it is requeued
    for nightly processing and the backend job record is marked failed.
    """
    from pipeline import model_router
    from pipeline.lightweight_config import should_skip_stage
    from worker.timeout_handler import JobTimeoutError, run_with_timeout

    job_id: str = job.get("jobId", "unknown")
    job_type: str = job.get("jobType", "")
    video_id: str = job.get("videoId", "")
    clip_id: str = job.get("clipId", "")
    input_uri: str = job.get("inputUri", "")
    priority: int = int(job.get("priority", 0))
    input_artifacts: dict[str, Any] = job.get("inputArtifacts", {})
    is_same_session = model_router.is_same_session(priority)

    pipeline_mode = "same_session" if is_same_session else "nightly"
    log.info(
        "processing_job",
        job_id=job_id,
        job_type=job_type,
        video_id=video_id,
        clip_id=clip_id,
        priority=priority,
        pipeline_mode=pipeline_mode,
    )

    from worker.observability import (
        record_heartbeat as _hb,
        record_job_failed as _jf,
        record_job_started as _js,
        record_job_succeeded as _jsuc,
        record_job_timed_out as _jto,
    )

    _js(job_type, pipeline_mode)
    _hb()
    job_start_time = time.time()

    if should_skip_stage(job_type, priority):
        log.info("stage_skipped_lightweight_path", job_type=job_type, job_id=job_id)
        _update_job_status(
            job_id,
            "succeeded",
            output_artifacts={
                "skipped": True,
                "reason": "same_session_lightweight_path",
            },
        )
        _jsuc(job_type, pipeline_mode, time.time() - job_start_time)
        return

    _update_job_status(job_id, "running")

    try:
        if is_same_session:
            artifacts = run_with_timeout(
                _dispatch,
                args=(
                    job_type,
                    video_id,
                    clip_id,
                    input_uri,
                    input_artifacts,
                    job_id,
                    priority,
                ),
                job_id=job_id,
                job_payload=job,
            )
        else:
            artifacts = _dispatch(
                job_type,
                video_id,
                clip_id,
                input_uri,
                input_artifacts,
                job_id,
                priority,
            )
        artifacts = dict(artifacts or {})
        routing = model_router.build_routing_artifact(job_type, priority)
        artifacts.setdefault("model_routing", {}).update(routing)
        if is_same_session:
            artifacts["pipeline_mode"] = "same_session"
        _update_job_status(job_id, "succeeded", output_artifacts=artifacts)
        _jsuc(job_type, pipeline_mode, time.time() - job_start_time)
        log.info(
            "job_succeeded",
            job_id=job_id,
            duration_seconds=round(time.time() - job_start_time, 2),
        )

        # After a same-session render completes, queue the nightly HLS follow-up.
        if is_same_session and job_type == "render":
            _queue_nightly_hls_followup(job, artifacts)

    except JobTimeoutError:
        _jto(job_type, pipeline_mode)
        log.warning("job_timeout_handled", job_id=job_id, priority=priority)
    except Exception as exc:
        _jf(job_type, pipeline_mode)
        log.error("job_failed", job_id=job_id, error=str(exc))
        _update_job_status(job_id, "failed", error_message=str(exc))


def _dispatch(
    job_type: str,
    video_id: str,
    clip_id: str,
    input_uri: str,
    input_artifacts: dict[str, Any],
    job_id: str,
    priority: int = 0,
) -> dict[str, Any]:
    """Route to the correct pipeline stage module."""
    from pipeline import (
        model_router,
        stage_calibrate,
        stage_coverage,
        stage_detect,
        stage_events,
        stage_ingest,
        stage_labels,
        stage_metrics,
        stage_oline,
        stage_reid,
        stage_render,
        stage_routes,
        stage_segment,
        stage_self_scout,
        stage_track,
        r2 as r2_mod,
    )

    if job_type == "ingest":
        return stage_ingest.run(video_id, input_uri, job_id)

    elif job_type == "segment":
        return stage_segment.run(video_id, input_uri, job_id)

    elif job_type == "calibrate":
        calib_variant = model_router.select_model("calibrate", priority)
        capture_regime = input_artifacts.get("capture_regime")
        return stage_calibrate.run(
            video_id,
            input_uri,
            job_id,
            variant=calib_variant,
            capture_regime=capture_regime,
        )

    elif job_type == "detect":
        detect_variant = model_router.select_model("detect", priority)
        capture_regime = input_artifacts.get("capture_regime")
        return stage_detect.run(
            video_id,
            input_uri,
            job_id,
            variant=detect_variant,
            capture_regime=capture_regime,
            priority=priority,
        )

    elif job_type == "track":
        detections: dict[str, Any] = input_artifacts.get("detections", {})
        fps: float = float(input_artifacts.get("fps", 30))
        track_variant = model_router.select_model("track", priority)
        return stage_track.run(clip_id, detections, fps, job_id, variant=track_variant)

    elif job_type == "reid":
        tracklet_ids: list[str] = input_artifacts.get("tracklet_ids", [])
        tracklets: list[dict[str, Any]] = input_artifacts.get("tracklets", [])
        roster: list[dict[str, Any]] = input_artifacts.get("roster", [])
        reid_variant = model_router.select_model("reid", priority)
        video_path = r2_mod.download_to_temp(_uri_to_r2_key(input_uri))
        try:
            return stage_reid.run(
                clip_id,
                video_path,
                tracklet_ids,
                tracklets,
                roster,
                BACKEND_API_URL,
                variant=reid_variant,
                priority=priority,
            )
        finally:
            video_path.unlink(missing_ok=True)

    elif job_type == "events":
        detections = input_artifacts.get("detections", {})
        fps = float(input_artifacts.get("fps", 30))
        # Optional multi-signal inputs (Issues #132/#134). When absent the
        # stage falls back to the legacy bbox-displacement heuristic.
        return stage_events.run(
            clip_id,
            detections,
            fps,
            job_id,
            tracklets=input_artifacts.get("tracklets"),
            ball_detections=input_artifacts.get("ball_detections"),
            pose_by_frame=input_artifacts.get("pose_by_frame"),
            ol_track_ids=input_artifacts.get("ol_track_ids"),
            qb_track_id=input_artifacts.get("qb_track_id"),
            center_track_id=input_artifacts.get("center_track_id"),
            defender_ids=input_artifacts.get("defender_ids"),
            homography=input_artifacts.get("homography"),
            los_band_px=input_artifacts.get("los_band_px"),
            los_prior=input_artifacts.get("los_prior"),
            end_of_play_frame=input_artifacts.get("end_of_play_frame"),
            goal_line_x=input_artifacts.get("goal_line_x"),
        )

    elif job_type == "labels":
        tracklets = input_artifacts.get("tracklets", [])
        events_list: list[dict[str, Any]] = input_artifacts.get("events", [])
        fps = float(input_artifacts.get("fps", 30))
        return stage_labels.run(clip_id, tracklets, events_list, fps, input_uri)

    elif job_type == "metrics":
        tracklets = input_artifacts.get("tracklets", [])
        events_list = input_artifacts.get("events", [])
        analytics_safe: bool = bool(input_artifacts.get("analytics_safe", False))
        fps = float(input_artifacts.get("fps", 30))
        return stage_metrics.run(
            clip_id, tracklets, events_list, analytics_safe, fps, job_id
        )

    elif job_type == "routes":
        tracklets = input_artifacts.get("tracklets", [])
        events_list = input_artifacts.get("events", [])
        fps = float(input_artifacts.get("fps", 30))
        return stage_routes.run(clip_id, tracklets, events_list, fps)

    elif job_type == "coverage":
        tracklets = input_artifacts.get("tracklets", [])
        events_list = input_artifacts.get("events", [])
        fps = float(input_artifacts.get("fps", 30))
        return stage_coverage.run(clip_id, tracklets, events_list, fps)

    elif job_type == "oline":
        tracklets = input_artifacts.get("tracklets", [])
        events_list = input_artifacts.get("events", [])
        analytics_safe = bool(input_artifacts.get("analytics_safe", False))
        fps = float(input_artifacts.get("fps", 30))
        return stage_oline.run(
            clip_id, tracklets, events_list, analytics_safe, fps, job_id
        )

    elif job_type == "self_scout":
        from pipeline import backend as backend_mod

        video_id_for_scout = input_artifacts.get("video_id")
        clips, labels_by_clip = backend_mod.fetch_clips_with_labels(
            video_id=video_id_for_scout,
        )
        metrics_by_clip: dict[str, list[dict[str, Any]]] = {}  # populated downstream
        return stage_self_scout.run(clips, labels_by_clip, metrics_by_clip)

    elif job_type == "pose":
        from pipeline import stage_pose, video_ingest

        model_path = os.environ.get("MODEL_POSE_PATH")
        tracklets = input_artifacts.get("tracklets", [])
        events_list = input_artifacts.get("events", [])
        analytics_safe = bool(input_artifacts.get("analytics_safe", False))
        fps = float(input_artifacts.get("fps", 30))

        # ``open_video`` silently falls back to ``MockVideoSource`` when the
        # URI is empty.  That is desirable in unit tests, but in a deployed
        # worker an empty ``input_uri`` for a pose job almost certainly means
        # the dispatcher dropped the artifact — log loudly so we don't silently
        # produce metrics from synthetic frames.
        if not input_uri:
            log.warning(
                "stage_pose_input_uri_missing_using_mock_source",
                job_id=job_id,
                clip_id=clip_id,
            )

        with video_ingest.open_video(input_uri or None, fps_fallback=fps) as source:
            return stage_pose.run(
                clip_id,
                source,
                tracklets,
                events_list,
                analytics_safe,
                fps,
                job_id,
                model_path,
            )

    elif job_type == "embeddings":
        # Nightly-only by design (issue #76 + docs/embeddings-architecture.md
        # §11). The variant ``play-embed-clip-vitb32-baseline`` is the only
        # one in NIGHTLY_ONLY_VARIANTS for ``embeddings`` so the routing
        # safety guard already prevents same-session execution.
        from pipeline import stage_embed
        from pipeline import backend as backend_mod

        variant = model_router.select_model("embeddings", priority)
        if variant == "none":
            log.info("stage_embed_skipped_no_variant", clip_id=clip_id)
            return {"embedding_skipped": True}
        if model_router.is_same_session(priority):
            log.warning(
                "stage_embed_rejected_same_session",
                clip_id=clip_id,
                priority=priority,
            )
            return {"embedding_skipped": True, "reason": "same_session_blocked"}

        model_version_id = input_artifacts.get("model_version_id")
        if not model_version_id:
            log.warning("stage_embed_missing_model_version_id", clip_id=clip_id)
            return {"embedding_skipped": True, "reason": "missing_model_version_id"}

        result = stage_embed.run(
            clip_id=clip_id,
            clip=input_artifacts.get("clip", {}),
            tracklets=input_artifacts.get("tracklets", []),
            track_points=input_artifacts.get("track_points", []),
            pose_keypoints=input_artifacts.get("pose_keypoints", []),
            labels=input_artifacts.get("labels", []),
            events=input_artifacts.get("events", []),
            fps=float(input_artifacts.get("fps", 60.0)),
            sam_masks=input_artifacts.get("sam_masks"),
        )
        backend_mod.create_play_embedding(
            clip_id=clip_id,
            model_version_id=str(model_version_id),
            vector=result.vector,
            visual_vector=result.visual_vector,
            structured_vector=result.structured_vector,
            chunk_kind=result.chunk_kind,
            snap_anchor=result.snap_anchor,
            used_sam_masks=result.used_sam_masks,
            embedding_confidence=result.embedding_confidence,
            source_label_ids=result.source_label_ids,
            calibration_version_id=input_artifacts.get("calibration_version_id"),
            is_experimental=True,
            job_id=job_id,
        )
        return {
            "embedding_written": True,
            "snap_anchor": result.snap_anchor,
            "used_sam_masks": result.used_sam_masks,
            "embedding_confidence": result.embedding_confidence,
        }

    elif job_type == "render":
        from pipeline.lightweight_config import use_period_renderer
        from renderer import period_renderer

        tracklets = input_artifacts.get("tracklets", [])
        labels_list: list[dict[str, Any]] = input_artifacts.get("labels", [])
        metrics_list: list[dict[str, Any]] = input_artifacts.get("metrics", [])
        analytics_safe = bool(input_artifacts.get("analytics_safe", False))
        fps = float(input_artifacts.get("fps", 30))
        video_path = r2_mod.download_to_temp(_uri_to_r2_key(input_uri))
        try:
            if use_period_renderer(priority):
                return period_renderer.run(
                    clip_id,
                    video_path,
                    tracklets,
                    labels_list,
                    analytics_safe,
                    fps,
                )
            return stage_render.run(
                clip_id,
                video_path,
                tracklets,
                labels_list,
                metrics_list,
                analytics_safe,
                fps,
                BACKEND_API_URL,
            )
        finally:
            video_path.unlink(missing_ok=True)

    elif job_type == "render_hls":
        from renderer import hls_encoder

        overlay_uri = input_artifacts.get("overlay_uri") or input_artifacts.get(
            "period_overlay_uri", ""
        )
        fps = float(input_artifacts.get("fps", 30))
        if not overlay_uri:
            log.warning("render_hls_missing_overlay_uri", job_id=job_id)
            return {"hls_skipped": True, "reason": "no_overlay_uri"}
        overlay_path = r2_mod.download_to_temp(_uri_to_r2_key(overlay_uri))
        try:
            return hls_encoder.run(clip_id, overlay_path, fps)
        finally:
            overlay_path.unlink(missing_ok=True)

    else:
        log.warning("unknown_job_type", job_type=job_type, job_id=job_id)
        return {}


def _uri_to_r2_key(uri: str) -> str:
    if uri.startswith("r2://"):
        return "/".join(uri.split("/")[3:])
    return uri


def _queue_nightly_hls_followup(
    original_job: dict[str, Any],
    render_artifacts: dict[str, Any],
) -> None:
    """Queue a nightly follow-up render_hls job after same-session render."""
    import uuid as _uuid

    from queue.same_session_queue import NIGHTLY_PRIORITY, push_nightly_job

    clip_id = original_job.get("clipId", "")
    video_id = original_job.get("videoId", "")
    overlay_uri = render_artifacts.get("period_overlay_uri") or render_artifacts.get(
        "overlay_uri", ""
    )
    followup_job_id = str(_uuid.uuid4())

    followup_payload: dict[str, Any] = {
        "jobId": followup_job_id,
        "jobType": "render_hls",
        "videoId": video_id,
        "clipId": clip_id,
        "inputUri": overlay_uri,
        "priority": NIGHTLY_PRIORITY,
        "inputArtifacts": {
            "overlay_uri": overlay_uri,
            "fps": render_artifacts.get("fps", 30),
            "pipeline_mode": "nightly",
            "_same_session_origin_job": original_job.get("jobId"),
        },
    }

    try:
        msg_id = push_nightly_job(followup_payload)
        log.info(
            "nightly_hls_followup_queued",
            followup_job_id=followup_job_id,
            clip_id=clip_id,
            message_id=msg_id,
        )
    except Exception as exc:
        log.error(
            "nightly_hls_followup_queue_failed",
            clip_id=clip_id,
            error=str(exc),
        )

    # Best-effort: create a backend job record for the follow-up.
    if BACKEND_API_URL:
        try:
            with httpx.Client(base_url=BACKEND_API_URL, timeout=10) as c:
                c.post(
                    "/api/v1/jobs",
                    json={
                        "id": followup_job_id,
                        "video_id": video_id,
                        "job_type": "render_hls",
                        "priority": NIGHTLY_PRIORITY,
                        "pipeline_mode": "nightly",
                        "input_artifacts": followup_payload["inputArtifacts"],
                    },
                )
        except Exception as exc:
            log.warning(
                "nightly_hls_followup_backend_create_failed",
                followup_job_id=followup_job_id,
                error=str(exc),
            )


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
    from worker.observability import (
        record_heartbeat,
        record_queue_poll,
        set_worker_up,
        start_metrics_server,
    )

    metrics_port = int(os.environ.get("GPU_METRICS_PORT", "9090"))
    try:
        start_metrics_server(port=metrics_port)
        log.info("metrics_server_started", port=metrics_port)
    except Exception as exc:
        log.warning("metrics_server_start_failed", port=metrics_port, error=str(exc))

    log.info("gpu_worker_starting", queue=QUEUE_NAME, poll_interval=POLL_INTERVAL)
    set_worker_up(True)
    record_heartbeat()

    with httpx.Client() as client:
        while not _shutdown:
            try:
                messages = pull_messages(client)
                record_queue_poll("success", len(messages))
                record_heartbeat()
                for msg in messages:
                    if _shutdown:
                        break
                    body: dict[str, Any] = msg.get("body", {})
                    lease_id: str = msg.get("lease_id", "")
                    process_job(body)
                    if lease_id:
                        ack_message(client, lease_id)

            except httpx.HTTPStatusError as exc:
                record_queue_poll("error")
                log.error(
                    "queue_pull_error", status=exc.response.status_code, error=str(exc)
                )
            except Exception as exc:
                record_queue_poll("error")
                log.error("worker_loop_error", error=str(exc))

            if not _shutdown:
                record_heartbeat()
                time.sleep(POLL_INTERVAL)

    set_worker_up(False)
    log.info("gpu_worker_stopped")


if __name__ == "__main__":
    main()
