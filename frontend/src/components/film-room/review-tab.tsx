"use client";

/**
 * Film Room → Review & Tag Plays.
 *
 * Real per-video clip inventory (replaces the old fake FieldStage "Clip
 * Review" panel): pick a video, list its processed clips from
 * /api/v1/videos/{id}/clips with play number / time range / result & review
 * state badges, and open each one in the real clip-review screen
 * (/clip-review/?clipId=…) with actual playback + overlays + corrections.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ClipStateBadges } from "@/components/clip-state-badge";
import { useAppState } from "@/lib/app-state";
import { useFetchState } from "@/lib/fetch-state";
import { fetchClipsForVideo } from "@/lib/api";
import { POSSESSION_LABEL, SESSION_KIND_LABEL } from "@/lib/labels";
import type { ApiClip, ApiVideo } from "@/lib/types";

export function ReviewTab() {
  const { data, authToken, apiStatus } = useAppState();
  const videos = data.videos;
  const [selectedVideoId, setSelectedVideoId] = useState<string>("");

  // Default to the most recently created processed video; fall back to the
  // newest video of any status so the picker is never silently empty.
  useEffect(() => {
    if (selectedVideoId && videos.some((v) => v.id === selectedVideoId)) return;
    const sorted = [...videos].sort(
      (a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""),
    );
    const preferred = sorted.find((v) => v.status === "ready") ?? sorted[0];
    setSelectedVideoId(preferred?.id ?? "");
  }, [videos, selectedVideoId]);

  const selectedVideo = videos.find((v) => v.id === selectedVideoId);

  const fetcher = useCallback(() => {
    if (!selectedVideoId) return Promise.resolve<ApiClip[]>([]);
    return fetchClipsForVideo(selectedVideoId, authToken);
  }, [selectedVideoId, authToken]);
  const { state, reload } = useFetchState(fetcher);

  const clips = useMemo(() => {
    if (state.kind !== "ready") return [];
    return [...state.data].sort((a, b) => {
      const ap = a.play_number ?? Number.MAX_SAFE_INTEGER;
      const bp = b.play_number ?? Number.MAX_SAFE_INTEGER;
      if (ap !== bp) return ap - bp;
      return a.start_time - b.start_time;
    });
  }, [state]);

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-12">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div>
            <h2 className="panel-title">Review &amp; Tag Plays</h2>
            <p className="kicker">
              Pick a video to see its detected plays. Each row opens the real
              clip-review screen — playback, tracking overlays, and coach
              corrections.
            </p>
          </div>
          <label className="form-control" style={{ minWidth: 260 }}>
            <span className="small-label">Video</span>
            <select
              value={selectedVideoId}
              onChange={(e) => setSelectedVideoId(e.target.value)}
              aria-label="Video to review"
              data-testid="review-video-picker"
              disabled={videos.length === 0}
            >
              {videos.length === 0 && <option value="">No videos yet</option>}
              {videos.map((v) => (
                <option key={v.id} value={v.id}>
                  {videoOptionLabel(v)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="panel panel-pad span-12">
        <h2 className="panel-title">
          Plays{selectedVideo ? ` — ${selectedVideo.filename}` : ""}
        </h2>
        {videos.length === 0 ? (
          <p className="kicker" style={{ marginTop: 8 }} data-testid="review-empty">
            {apiStatus === "loading" || apiStatus === "idle"
              ? "Loading film…"
              : apiStatus === "offline"
                ? "Backend offline — connect NEXT_PUBLIC_API_URL to review processed clips."
                : "No film yet. Upload video from the Upload / Process Film tab; clips appear here after processing."}
          </p>
        ) : (
          <>
            {state.kind === "loading" && (
              <p className="kicker" style={{ marginTop: 8 }}>Loading clips…</p>
            )}
            {state.kind === "offline" && (
              <p className="kicker" style={{ marginTop: 8 }}>
                Backend offline — connect NEXT_PUBLIC_API_URL to review processed clips.
              </p>
            )}
            {state.kind === "error" && (
              <div style={{ marginTop: 8 }}>
                <p className="kicker" style={{ color: "var(--accent-red, #f87171)" }}>
                  {state.message}
                </p>
                <button className="control-button" style={{ marginTop: 8 }} onClick={reload}>
                  Retry
                </button>
              </div>
            )}
            {state.kind === "empty" && (
              <p className="kicker" style={{ marginTop: 8 }} data-testid="review-no-clips">
                No clips processed for this video yet.
                {selectedVideo?.status === "uploaded"
                  ? " Start processing from the Upload / Process Film tab."
                  : selectedVideo?.status === "processing"
                    ? " Processing is still running — clips appear as play detection finishes."
                    : ""}
              </p>
            )}
            {state.kind === "ready" && (
              <div className="list-stack" style={{ marginTop: 10, gap: 6 }}>
                {clips.map((clip) => (
                  <ReviewClipRow key={clip.id} clip={clip} />
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function ReviewClipRow({ clip }: { clip: ApiClip }) {
  const possession = clip.our_possession ?? clip.side_of_ball ?? null;
  const possessionLabel = possession ? POSSESSION_LABEL[possession] : null;
  const isPreliminary =
    clip.is_preliminary === true || clip.result_state === "preliminary";
  return (
    <Link
      href={`/clip-review/?clipId=${encodeURIComponent(clip.id)}`}
      className="row-button"
      data-testid={`review-clip-${clip.id}`}
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 8,
        textDecoration: "none",
        color: "inherit",
        padding: "8px 10px",
        border: "1px solid var(--line-soft, #333)",
        borderRadius: 6,
      }}
    >
      <div style={{ minWidth: 0 }}>
        <strong>
          {clip.play_number != null ? `Play #${clip.play_number}` : `Clip ${clip.id.slice(0, 8)}`}
        </strong>
        <div className="kicker" style={{ marginTop: 2 }}>
          {formatClock(clip.start_time)}–{formatClock(clip.end_time)}
          {" · "}
          {(clip.end_time - clip.start_time).toFixed(1)}s
          {possessionLabel ? ` · ${possessionLabel}` : ""}
          {clip.session_kind ? ` · ${SESSION_KIND_LABEL[clip.session_kind]}` : ""}
          {clip.confidence != null ? ` · ${Math.round(clip.confidence * 100)}%` : ""}
        </div>
      </div>
      <span style={{ display: "inline-flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
        <ClipStateBadges
          isPreliminary={isPreliminary}
          reviewState={clip.review_state}
        />
        <span className="status-pill info">Review →</span>
      </span>
    </Link>
  );
}

function videoOptionLabel(v: ApiVideo): string {
  const date = (v.recorded_at ?? v.created_at ?? "").slice(0, 10);
  return `${date ? `${date} · ` : ""}${v.filename} (${v.status})`;
}

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
