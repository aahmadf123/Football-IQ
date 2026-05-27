"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FootballShell } from "@/components/football-shell";
import { useAppState } from "@/lib/app-state";
import {
  fetchClip,
  fetchClipOverlays,
  fetchVideo,
  fetchVideoDownloadUrl,
  parseStorageUri,
} from "@/lib/api";
import type {
  ApiClip,
  ApiVideo,
  ClipOverlayPayload,
  OverlayLayerKey,
  OurPossession,
  SessionKind,
} from "@/lib/types";
import { OverlayCanvas, eventTimeSeconds } from "./overlay-canvas";

const POSSESSION_LABEL: Record<OurPossession, string> = {
  offense: "Toledo Offense",
  defense: "Toledo Defense",
  special_teams: "Special Teams",
};

const SESSION_KIND_LABEL: Record<SessionKind, string> = {
  practice: "Practice",
  scrimmage: "Scrimmage",
  game: "Game",
};

const LAYER_TOGGLES: ReadonlyArray<{ key: OverlayLayerKey; label: string }> = [
  { key: "raw", label: "Raw" },
  { key: "tracks", label: "Tracks" },
  { key: "labels", label: "Labels" },
  { key: "events", label: "Events" },
  { key: "metrics", label: "Metrics" },
  { key: "wireframe", label: "Wireframe" },
];

// Default playback frame rate when the parent video has no ``fps`` recorded.
// Phase CV pipeline targets 30fps; overlays sync to this by default so the
// player→frame conversion is still meaningful before metadata is filled in.
const DEFAULT_FPS = 30;

type ReviewState =
  | { kind: "loading" }
  | { kind: "offline" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      clip: ApiClip;
      video: ApiVideo;
      playbackUrl: string | null;
      playbackUnavailable: "none" | "no_storage_uri" | "url_generation_failed";
    };

type OverlayState =
  | { kind: "loading" }
  | { kind: "empty"; payload: ClipOverlayPayload }
  | { kind: "ready"; payload: ClipOverlayPayload }
  | { kind: "error"; message: string };

export default function ClipReviewPage() {
  return (
    <FootballShell activePage="clip-review">
      <Suspense fallback={<section className="panel panel-pad"><p className="kicker">Loading…</p></section>}>
        <ClipReviewLoader />
      </Suspense>
    </FootballShell>
  );
}

function ClipReviewLoader() {
  const searchParams = useSearchParams();
  const clipId = searchParams.get("clipId") ?? "";
  if (!clipId) {
    return (
      <section className="panel panel-pad">
        <h3 className="panel-title">No clip selected</h3>
        <p className="kicker" style={{ marginTop: 8 }}>
          Open a clip from the{" "}
          <Link href="/library" style={{ color: "var(--gold)" }}>Library</Link>{" "}
          to review it.
        </p>
      </section>
    );
  }
  return <ClipReviewView clipId={clipId} />;
}

function ClipReviewView({ clipId }: { clipId: string }) {
  const { authToken } = useAppState();
  const [state, setState] = useState<ReviewState>({ kind: "loading" });
  const [overlayState, setOverlayState] = useState<OverlayState>({ kind: "loading" });

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setState({ kind: "offline" });
      setOverlayState({ kind: "loading" });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const clip = await fetchClip(clipId, authToken);
        const video = await fetchVideo(clip.video_id, authToken);
        let playbackUrl: string | null = null;
        let playbackUnavailable: "none" | "no_storage_uri" | "url_generation_failed" = "none";
        try {
          const clipStorage = parseStorageUri(clip.storage_uri);
          const videoStorage = parseStorageUri(video.storage_uri);
          const target = clipStorage ?? videoStorage;
          if (!target) {
            playbackUnavailable = "no_storage_uri";
          } else {
            playbackUrl = await fetchVideoDownloadUrl(target.bucket, target.key, authToken);
            if (!playbackUrl) playbackUnavailable = "url_generation_failed";
          }
        } catch {
          playbackUnavailable = "url_generation_failed";
        }
        if (cancelled) return;
        setState({ kind: "ready", clip, video, playbackUrl, playbackUnavailable });
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clipId, authToken]);

  // Overlay fetch is independent of the clip fetch — a clip with no overlays
  // (e.g. ingest still running) should still render the player + metadata.
  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) return;
    let cancelled = false;
    setOverlayState({ kind: "loading" });
    (async () => {
      try {
        const payload = await fetchClipOverlays(clipId, authToken);
        if (cancelled) return;
        const empty =
          !payload.layers_available.tracklets &&
          !payload.layers_available.events &&
          !payload.layers_available.labels &&
          !payload.layers_available.metrics;
        setOverlayState(empty ? { kind: "empty", payload } : { kind: "ready", payload });
      } catch (err) {
        if (cancelled) return;
        setOverlayState({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clipId, authToken]);

  if (state.kind === "loading") {
    return (
      <section className="panel panel-pad">
        <p className="kicker">Loading clip metadata…</p>
      </section>
    );
  }
  if (state.kind === "offline") {
    return (
      <section className="panel panel-pad">
        <h3 className="panel-title">Backend not configured</h3>
        <p className="kicker" style={{ marginTop: 8 }}>
          Clip Review requires <code>NEXT_PUBLIC_API_URL</code>.
        </p>
        <Link href="/library" className="control-button" style={{ marginTop: 12 }}>
          ← Back to Library
        </Link>
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section className="panel panel-pad">
        <h3 className="panel-title">Could not load clip</h3>
        <p className="kicker" style={{ marginTop: 8, color: "var(--accent-red, #f87171)" }}>
          {state.message}
        </p>
        <Link href="/library" className="control-button" style={{ marginTop: 12 }}>
          ← Back to Library
        </Link>
      </section>
    );
  }

  return <ClipReviewReady state={state} overlayState={overlayState} />;
}

function ClipReviewReady({
  state,
  overlayState,
}: {
  state: Extract<ReviewState, { kind: "ready" }>;
  overlayState: OverlayState;
}) {
  const { clip, video, playbackUrl, playbackUnavailable } = state;
  const possession = clip.our_possession ?? clip.side_of_ball ?? video.our_possession ?? null;
  const possessionLabel = possession ? POSSESSION_LABEL[possession] : null;
  const sessionKindLabel = clip.session_kind
    ? SESSION_KIND_LABEL[clip.session_kind]
    : video.session_kind
      ? SESSION_KIND_LABEL[video.session_kind]
      : "Session";

  const fps = video.fps ?? DEFAULT_FPS;
  const [activeLayers, setActiveLayers] = useState<Set<OverlayLayerKey>>(
    () => new Set<OverlayLayerKey>(["tracks", "events", "labels", "metrics"]),
  );
  const playbackUsesClipAsset = Boolean(clip.storage_uri);
  // Parent-video playback uses full-video time and must be shifted into the
  // clip timeline. Rendered clip playback already starts at clip-local time 0.
  const [videoCurrentTime, setVideoCurrentTime] = useState(0);
  const clipLocalTime = playbackUsesClipAsset
    ? Math.max(0, videoCurrentTime)
    : Math.max(0, videoCurrentTime - clip.start_time);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const onTimeUpdate = useCallback(() => {
    const el = videoRef.current;
    if (el) setVideoCurrentTime(el.currentTime);
  }, []);

  const toggleLayer = useCallback((key: OverlayLayerKey) => {
    setActiveLayers((prev) => {
      const next = new Set(prev);
      if (key === "raw") {
        // ``raw`` is mutually exclusive — it clears every overlay layer.
        return new Set<OverlayLayerKey>(prev.has("raw") ? ["tracks", "events", "labels", "metrics"] : ["raw"]);
      }
      if (next.has("raw")) next.delete("raw");
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const overlayPayload = overlayState.kind === "ready" || overlayState.kind === "empty"
    ? overlayState.payload
    : null;

  const overlayLayersForCanvas = useMemo(() => {
    if (activeLayers.has("raw")) return new Set<OverlayLayerKey>();
    return activeLayers;
  }, [activeLayers]);

  const eventsForTimeline = useMemo(() => {
    if (!overlayPayload) return [];
    return overlayPayload.events
      .map((e) => ({ event: e, t: eventTimeSeconds(e, fps) }))
      .filter((row): row is { event: typeof row.event; t: number } => row.t != null);
  }, [overlayPayload, fps]);

  return (
    <div className="content-grid">
      <section className="panel span-8 panel-pad">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <div>
            <h2 className="panel-title">
              {clip.play_number != null
                ? `Play #${clip.play_number}`
                : `Clip ${clip.id.slice(0, 8)}`}
            </h2>
            <p className="kicker">
              {sessionKindLabel}
              {video.opponent_team ? ` · vs. ${video.opponent_team}` : ""}
              {possessionLabel ? ` · ${possessionLabel}` : ""}
            </p>
          </div>
          <Link href="/library" className="control-button">← Library</Link>
        </div>

        <div
          style={{
            marginTop: 12,
            background: "#000",
            borderRadius: 8,
            minHeight: 320,
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {playbackUrl ? (
            <>
              <video
                ref={videoRef}
                src={playbackUrl}
                controls
                playsInline
                onTimeUpdate={onTimeUpdate}
                onSeeked={onTimeUpdate}
                aria-label={`Clip ${clip.play_number ?? clip.id} video`}
                style={{ width: "100%", maxHeight: 480, display: "block" }}
              />
              {overlayPayload && (
                <OverlayCanvas
                  tracklets={overlayPayload.tracklets}
                  events={overlayPayload.events}
                  currentTimeSeconds={clipLocalTime}
                  fps={fps}
                  videoWidth={video.width ?? null}
                  videoHeight={video.height ?? null}
                  activeLayers={overlayLayersForCanvas}
                />
              )}
            </>
          ) : (
            <div style={{ color: "var(--muted, #94a3b8)", textAlign: "center", padding: 24 }}>
              <p style={{ margin: 0, fontWeight: 700 }}>Video not available</p>
              <p className="kicker" style={{ marginTop: 8 }}>
                {playbackUnavailable === "no_storage_uri"
                  ? "No storage URI found. The video may not have been uploaded or rendered yet."
                  : "Video playback failed or is unavailable. The Worker may not be deployed, the signed URL may have been rejected, or the file may be missing from storage."}
              </p>
            </div>
          )}
        </div>

        <p className="kicker" style={{ marginTop: 8 }}>
          {clip.start_time.toFixed(1)}s – {clip.end_time.toFixed(1)}s
          {" "}({(clip.end_time - clip.start_time).toFixed(1)}s duration)
        </p>

        <OverlayToggles
          active={activeLayers}
          overlayState={overlayState}
          onToggle={toggleLayer}
        />

        {overlayPayload && (
          <EventTimeline
            events={eventsForTimeline}
            clipDuration={clip.end_time - clip.start_time}
          />
        )}
      </section>

      <aside className="panel panel-pad span-4">
        <h2 className="panel-title">Clip Metadata</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          <MetadataRow label="Video" value={video.filename} />
          <MetadataRow label="Video status" value={video.status} />
          <MetadataRow label="Session" value={sessionKindLabel} />
          {video.opponent_team && (
            <MetadataRow label="Opponent" value={video.opponent_team} />
          )}
          {possessionLabel && (
            <MetadataRow label="Possession" value={possessionLabel} />
          )}
          {clip.play_number != null && (
            <MetadataRow label="Play #" value={String(clip.play_number)} />
          )}
          <MetadataRow
            label="Boundaries"
            value={`${clip.start_time.toFixed(1)}s → ${clip.end_time.toFixed(1)}s`}
          />
          {clip.confidence != null && (
            <MetadataRow
              label="Confidence"
              value={`${Math.round(clip.confidence * 100)}%`}
            />
          )}
          <MetadataRow
            label="Reviewed"
            value={
              clip.is_reviewed === true
                ? "Yes"
                : clip.is_reviewed === false
                  ? "No"
                  : "Unknown"
            }
          />
          {video.recorded_at && (
            <MetadataRow
              label="Recorded"
              value={new Date(video.recorded_at).toLocaleString()}
            />
          )}
        </div>

        <OverlaySummary
          overlayState={overlayState}
          showMetrics={activeLayers.has("metrics") && !activeLayers.has("raw")}
          showLabels={activeLayers.has("labels") && !activeLayers.has("raw")}
        />

        <h3 className="panel-title" style={{ marginTop: 16 }}>Storage</h3>
        <p className="kicker" style={{ wordBreak: "break-all" }}>
          {clip.storage_uri ?? "Clip not yet rendered to R2."}
        </p>
      </aside>
    </div>
  );
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span className="small-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function OverlayToggles({
  active,
  overlayState,
  onToggle,
}: {
  active: ReadonlySet<OverlayLayerKey>;
  overlayState: OverlayState;
  onToggle: (key: OverlayLayerKey) => void;
}) {
  const layersAvailable =
    overlayState.kind === "ready" || overlayState.kind === "empty"
      ? overlayState.payload.layers_available
      : null;
  return (
    <div
      data-testid="overlay-toggles"
      role="group"
      aria-label="Overlay layer toggles"
      style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}
    >
      {LAYER_TOGGLES.map((layer) => {
        const isActive = active.has(layer.key);
        // ``raw`` and ``wireframe`` are always available; data layers report
        // their availability so coaches know why a toggle is dimmed.
        const layerHasData =
          layer.key === "raw" || layer.key === "wireframe"
            ? true
            : layersAvailable
              ? layersAvailable[layerKeyToAvailability(layer.key)]
              : true;
        return (
          <button
            key={layer.key}
            type="button"
            onClick={() => onToggle(layer.key)}
            aria-pressed={isActive}
            data-testid={`overlay-toggle-${layer.key}`}
            disabled={!layerHasData && layer.key !== "raw"}
            style={{
              padding: "4px 10px",
              borderRadius: 999,
              border: `1px solid ${isActive ? "var(--gold)" : "rgba(148,163,184,0.4)"}`,
              background: isActive ? "rgba(251,191,36,0.18)" : "transparent",
              color: isActive ? "var(--gold)" : "var(--muted, #94a3b8)",
              fontSize: 12,
              cursor: layerHasData ? "pointer" : "not-allowed",
              opacity: layerHasData ? 1 : 0.55,
            }}
          >
            {layer.label}
            {!layerHasData && layer.key !== "raw" && layer.key !== "wireframe"
              ? " · empty"
              : ""}
          </button>
        );
      })}
    </div>
  );
}

function layerKeyToAvailability(
  key: OverlayLayerKey,
): keyof ClipOverlayPayload["layers_available"] {
  switch (key) {
    case "tracks":
      return "tracklets";
    case "events":
      return "events";
    case "labels":
      return "labels";
    case "metrics":
      return "metrics";
    default:
      return "tracklets";
  }
}

function EventTimeline({
  events,
  clipDuration,
}: {
  events: ReadonlyArray<{ event: { id: string; event_type: string }; t: number }>;
  clipDuration: number;
}) {
  if (clipDuration <= 0) return null;
  if (events.length === 0) {
    return (
      <p
        data-testid="event-timeline-empty"
        className="kicker"
        style={{ marginTop: 12 }}
      >
        No events tagged for this clip.
      </p>
    );
  }
  return (
    <div
      data-testid="event-timeline"
      style={{
        marginTop: 12,
        position: "relative",
        height: 28,
        borderRadius: 4,
        background: "rgba(148,163,184,0.12)",
      }}
      aria-label="Event timeline"
    >
      {events.map(({ event, t }) => {
        const pct = Math.min(1, Math.max(0, t / clipDuration));
        return (
          <div
            key={event.id}
            data-testid={`event-marker-${event.id}`}
            title={event.event_type}
            style={{
              position: "absolute",
              top: 4,
              bottom: 4,
              left: `${pct * 100}%`,
              width: 4,
              transform: "translateX(-2px)",
              background: "var(--gold, #fbbf24)",
              borderRadius: 2,
            }}
          />
        );
      })}
    </div>
  );
}

function OverlaySummary({
  overlayState,
  showMetrics,
  showLabels,
}: {
  overlayState: OverlayState;
  showMetrics: boolean;
  showLabels: boolean;
}) {
  if (overlayState.kind === "loading") {
    return (
      <p data-testid="overlay-loading" className="kicker" style={{ marginTop: 16 }}>
        Loading overlays…
      </p>
    );
  }
  if (overlayState.kind === "error") {
    return (
      <p
        data-testid="overlay-error"
        className="kicker"
        style={{ marginTop: 16, color: "var(--accent-red, #f87171)" }}
      >
        Could not load overlays: {overlayState.message}
      </p>
    );
  }
  if (overlayState.kind === "empty") {
    return (
      <p data-testid="overlay-empty" className="kicker" style={{ marginTop: 16 }}>
        No overlays available for this clip yet.
      </p>
    );
  }

  const { payload } = overlayState;
  const missing = [
    payload.layers_available.tracklets ? null : "tracklets",
    payload.layers_available.events ? null : "events",
    payload.layers_available.labels ? null : "labels",
    payload.layers_available.metrics ? null : "metrics",
  ].filter((x): x is string => x != null);

  return (
    <div data-testid="overlay-summary" style={{ marginTop: 16 }}>
      <h3 className="panel-title">Overlays</h3>
      {missing.length > 0 && (
        <p
          data-testid="overlay-degraded"
          className="kicker"
          style={{ marginTop: 4 }}
        >
          Missing layers: {missing.join(", ")}.
        </p>
      )}
      {showLabels && payload.labels.length > 0 && (
        <div data-testid="overlay-labels-list" style={{ marginTop: 8 }}>
          <p className="small-label">Labels</p>
          <ul style={{ paddingLeft: 18, margin: "4px 0" }}>
            {payload.labels.slice(0, 6).map((lb) => (
              <li key={lb.id}>
                <strong>{lb.label_type}</strong>
                {": "}
                <span className="kicker">
                  {summarizeLabelValue(lb.label_value)} · {lb.source}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {showMetrics && payload.metrics.length > 0 && (
        <div data-testid="overlay-metrics-list" style={{ marginTop: 8 }}>
          <p className="small-label">Metrics</p>
          <ul style={{ paddingLeft: 18, margin: "4px 0" }}>
            {payload.metrics.slice(0, 8).map((m) => (
              <li key={m.id}>
                <strong>{m.metric_name}</strong>
                {": "}
                <span className="kicker">
                  {summarizeMetricValue(m.metric_value)}
                  {m.unit ? ` ${m.unit}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function summarizeLabelValue(value: Record<string, unknown>): string {
  if ("name" in value && typeof value.name === "string") return value.name;
  const entries = Object.entries(value).slice(0, 2);
  return entries.map(([k, v]) => `${k}=${String(v)}`).join(", ");
}

function summarizeMetricValue(value: Record<string, unknown>): string {
  if ("value" in value) return String(value.value);
  const entries = Object.entries(value).slice(0, 2);
  return entries.map(([k, v]) => `${k}=${String(v)}`).join(", ");
}
