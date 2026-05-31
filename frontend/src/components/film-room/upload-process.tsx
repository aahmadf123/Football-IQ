"use client";

import { Trash2, Upload } from "lucide-react";
import { useCallback, useState } from "react";
import { PreliminaryBadge } from "@/components/clip-state-badge";
import {
  requestVideoProcessing,
  WorkloadGatedError,
  type VideoInboxItem,
} from "@/lib/api";
import { useAppState, type UploadPhase } from "@/lib/app-state";

// Per-video local request state, layered on top of the backend inbox status so
// the coach gets immediate "Queued" feedback before the backend reflects it.
type RequestState =
  | { kind: "queued" }
  | { kind: "busy"; message: string }
  | { kind: "error"; message: string };

function phaseLabel(phase: UploadPhase): string {
  switch (phase) {
    case "idle":
      return "Queued to upload";
    case "requesting-url":
      return "Preparing…";
    case "uploading":
      return "Uploading…";
    case "registering":
      return "Saving…";
    case "done":
      return "Uploaded";
    case "error":
      return "Upload failed";
  }
}

function phaseColor(phase: UploadPhase): string {
  switch (phase) {
    case "done":
      return "var(--accent-green, #4ade80)";
    case "error":
      return "var(--accent-red, #f87171)";
    case "uploading":
    case "registering":
    case "requesting-url":
      return "var(--accent-amber, #fbbf24)";
    default:
      return "var(--text-muted, #94a3b8)";
  }
}

// Coach-facing label + tone for a backend video status. The five lifecycle
// states (uploaded → queued → processing → processed → failed) are preserved.
function statusBadge(
  videoStatus: string,
  request: RequestState | undefined,
): { label: string; color: string } {
  if (request?.kind === "queued" && videoStatus === "uploaded") {
    return { label: "Queued", color: "var(--accent-amber, #fbbf24)" };
  }
  switch (videoStatus) {
    case "ready":
      return { label: "Processed", color: "var(--accent-green, #4ade80)" };
    case "processing":
      return { label: "Processing", color: "var(--accent-amber, #fbbf24)" };
    case "failed":
      return { label: "Failed", color: "var(--accent-red, #f87171)" };
    case "uploaded":
    default:
      return { label: "Uploaded", color: "var(--text-muted, #94a3b8)" };
  }
}

export function UploadProcessFilm({ onUploadClick }: { onUploadClick: () => void }) {
  const {
    uploads,
    removeUpload,
    retryUpload,
    inboxItems,
    refreshInbox,
    apiStatus,
    mockMode,
    authToken,
  } = useAppState();

  const [requests, setRequests] = useState<Record<string, RequestState>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});

  const handleProcess = useCallback(
    async (videoId: string) => {
      setPending((cur) => ({ ...cur, [videoId]: true }));
      setRequests((cur) => {
        const next = { ...cur };
        delete next[videoId];
        return next;
      });
      try {
        await requestVideoProcessing(videoId, { mode: "nightly" }, authToken);
        setRequests((cur) => ({ ...cur, [videoId]: { kind: "queued" } }));
        refreshInbox();
      } catch (err) {
        if (err instanceof WorkloadGatedError) {
          setRequests((cur) => ({ ...cur, [videoId]: { kind: "busy", message: err.message } }));
        } else {
          setRequests((cur) => ({
            ...cur,
            [videoId]: {
              kind: "error",
              message: err instanceof Error ? err.message : String(err),
            },
          }));
        }
      } finally {
        setPending((cur) => ({ ...cur, [videoId]: false }));
      }
    },
    [authToken, refreshInbox],
  );

  const inFlight = uploads.filter((u) => u.phase !== "done");

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
            <h2 className="panel-title">Upload &amp; Process Film</h2>
            <p className="kicker">
              Add practice or game film here. Uploaded film is saved but{" "}
              <strong>not processed automatically</strong> — click{" "}
              <strong>Process Film</strong> when you&rsquo;re ready to run the
              pipeline. Full-quality processing runs in the overnight queue.
            </p>
          </div>
          <button className="control-button primary" onClick={onUploadClick}>
            <Upload size={15} /> Upload Film
          </button>
        </div>
      </section>

      {inFlight.length > 0 && (
        <section className="panel panel-pad span-12">
          <h2 className="panel-title">Uploading now</h2>
          <div className="list-stack" style={{ marginTop: 10 }}>
            {inFlight.map((u) => (
              <div
                key={u.id}
                className="status-row"
                style={{ gridTemplateColumns: "1fr auto auto" }}
              >
                <div>
                  <strong>{u.filename}</strong>
                  <div className="kicker">
                    {(u.sizeBytes / (1024 * 1024)).toFixed(1)} MB{" · "}
                    <span style={{ color: phaseColor(u.phase), fontWeight: 700 }}>
                      {phaseLabel(u.phase)}
                      {u.phase === "uploading" && ` ${u.progress}%`}
                    </span>
                  </div>
                  {u.phase === "uploading" && (
                    <div style={{ height: 3, background: "var(--line-soft, #333)", borderRadius: 2, marginTop: 4 }}>
                      <div style={{ height: "100%", width: `${u.progress}%`, background: "var(--accent-amber, #fbbf24)", borderRadius: 2, transition: "width 0.3s" }} />
                    </div>
                  )}
                  {u.phase === "error" && u.error && (
                    <div className="kicker" style={{ color: "var(--accent-red, #f87171)", marginTop: 2 }}>
                      {u.error}
                    </div>
                  )}
                </div>
                {u.phase === "error" && (
                  <button className="control-button" onClick={() => retryUpload(u.id)}>
                    Retry upload
                  </button>
                )}
                <button
                  className="control-button"
                  onClick={() => removeUpload(u.id)}
                  aria-label={`Remove ${u.filename}`}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel panel-pad span-12">
        <h2 className="panel-title">Film &amp; processing status</h2>
        <ProcessingList
          items={inboxItems}
          apiStatus={apiStatus}
          mockMode={mockMode}
          requests={requests}
          pending={pending}
          onProcess={handleProcess}
        />
      </section>
    </div>
  );
}

function ProcessingList({
  items,
  apiStatus,
  mockMode,
  requests,
  pending,
  onProcess,
}: {
  items: VideoInboxItem[];
  apiStatus: ReturnType<typeof useAppState>["apiStatus"];
  mockMode: boolean;
  requests: Record<string, RequestState>;
  pending: Record<string, boolean>;
  onProcess: (videoId: string) => void;
}) {
  if (items.length === 0) {
    const message =
      apiStatus === "loading" || apiStatus === "idle"
        ? "Checking for uploaded film…"
        : apiStatus === "offline"
          ? "Backend offline — connect NEXT_PUBLIC_API_URL to see uploaded film and start processing."
          : mockMode
            ? "Mock mode is on — only server-backed film appears here. Configure the backend to process real film."
            : "No film waiting. Upload practice or game film above, then start processing when you're ready.";
    return (
      <p className="kicker" style={{ marginTop: 8 }} data-testid="processing-empty">
        {message}
      </p>
    );
  }

  return (
    <div className="list-stack" style={{ marginTop: 10, gap: 8 }}>
      {items.map((item) => (
        <ProcessingRow
          key={item.video_id}
          item={item}
          request={requests[item.video_id]}
          pending={!!pending[item.video_id]}
          onProcess={onProcess}
        />
      ))}
    </div>
  );
}

function ProcessingRow({
  item,
  request,
  pending,
  onProcess,
}: {
  item: VideoInboxItem;
  request: RequestState | undefined;
  pending: boolean;
  onProcess: (videoId: string) => void;
}) {
  const isQueued = request?.kind === "queued";
  const badge = isQueued
    ? { label: "Queued", color: "var(--accent-amber, #fbbf24)" }
    : statusBadge(item.video_status, request);
  const canProcess = item.video_status === "uploaded" && !isQueued;
  const isFailed = item.video_status === "failed" && !isQueued;

  return (
    <div
      data-testid={`processing-row-${item.video_id}`}
      style={{
        border: "1px solid var(--line-soft, #333)",
        borderRadius: 8,
        padding: 12,
        display: "flex",
        gap: 12,
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
          <strong>{item.filename}</strong>
          <span
            data-testid={`processing-status-${item.video_id}`}
            style={{ color: badge.color, fontWeight: 700, fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.04em" }}
          >
            {badge.label}
          </span>
          {(item.preliminary_clip_count ?? 0) > 0 && <PreliminaryBadge />}
        </div>
        <div className="kicker" style={{ marginTop: 4 }}>
          {item.video_status === "uploaded" && !isQueued
            ? "Not processed yet — start processing when you're ready."
            : isQueued
              ? "Queued for full-quality processing."
              : item.video_status === "processing"
                ? `Processing… ${item.succeeded_jobs}/${item.total_jobs} jobs done`
                : item.video_status === "ready"
                  ? `Processed · ${item.clip_count} clip${item.clip_count === 1 ? "" : "s"}`
                  : item.video_status === "failed"
                    ? `Processing failed${item.latest_error_stage ? ` at ${item.latest_error_stage}` : ""}.`
                    : null}
        </div>
        {(item.preliminary_clip_count ?? 0) > 0 && (
          <div
            className="kicker"
            data-testid={`processing-preliminary-${item.video_id}`}
            style={{ marginTop: 2 }}
          >
            {item.preliminary_clip_count} preliminary clip
            {item.preliminary_clip_count === 1 ? "" : "s"} — full-quality nightly
            upgrade pending.
          </div>
        )}
        {isFailed && item.latest_error_message && (
          <div className="kicker" style={{ color: "var(--accent-red, #f87171)", marginTop: 2 }}>
            {item.latest_error_message}
          </div>
        )}
        {request?.kind === "busy" && (
          <div className="kicker" style={{ color: "var(--accent-amber, #fbbf24)", marginTop: 2 }} data-testid={`processing-busy-${item.video_id}`}>
            {request.message}
          </div>
        )}
        {request?.kind === "error" && (
          <div className="kicker" style={{ color: "var(--accent-red, #f87171)", marginTop: 2 }} data-testid={`processing-error-${item.video_id}`}>
            {request.message}
          </div>
        )}
      </div>
      {canProcess && (
        <button
          className="control-button primary"
          data-testid={`process-film-${item.video_id}`}
          onClick={() => onProcess(item.video_id)}
          disabled={pending}
        >
          {pending ? "Starting…" : "Process Film"}
        </button>
      )}
      {isFailed && (
        <button
          className="control-button"
          data-testid={`retry-process-${item.video_id}`}
          onClick={() => onProcess(item.video_id)}
          disabled={pending}
        >
          {pending ? "Starting…" : "Retry processing"}
        </button>
      )}
    </div>
  );
}
