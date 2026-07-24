"use client";

/**
 * Dashboard — real backend surfaces only (extracted from the old
 * page-renderer monolith, minus its decorative mock widgets):
 *
 *   - Practice Inbox: per-video processing status from /api/v1/inbox/status
 *   - Recent Film: videos from the shared app-state fetch (+ upload trigger)
 *   - Processing Jobs: /api/v1/jobs with the per-stage `progress` map
 *   - Coaching Alerts: latest rows from /api/v1/alerts
 *
 * Every card renders honest loading/offline/empty states instead of sample
 * numbers (repo rule #96).
 */

import Link from "next/link";
import { Upload } from "lucide-react";
import { useCallback } from "react";
import { useAppState, type ApiStatus } from "@/lib/app-state";
import { useFetchState } from "@/lib/fetch-state";
import { fetchAlerts, fetchJobs, type ApiAlert, type VideoInboxItem } from "@/lib/api";
import { useUploadWidget } from "@/components/shared/upload-widget";
import type { ApiJob, ApiVideo, JobStageProgress } from "@/lib/types";

export function DashboardView() {
  const { openFilePicker, widget } = useUploadWidget();
  return (
    <>
      {widget}
      <div className="content-grid">
        <PracticeInboxSection />
        <RecentFilmCard onUploadClick={openFilePicker} />
        <JobsCard />
        <AlertsSummaryCard />
      </div>
    </>
  );
}

// ── Practice Inbox ───────────────────────────────────────────────────────────

function PracticeInboxSection() {
  const { inboxItems, data, mockMode, apiStatus } = useAppState();
  const jobs = data.jobs;

  // Outside mock mode, never substitute a fake job-based view. Distinguish
  // a genuinely empty inbox from "still connecting" or "backend offline" so
  // the UI does not appear successful when the backend has no inbox data or
  // is not reachable.
  if (!mockMode && inboxItems.length === 0) {
    const isLoading = apiStatus === "loading" || apiStatus === "idle";
    const isOffline = apiStatus === "offline";
    return (
      <section className="panel panel-pad span-12">
        <h2 className="panel-title">Practice Inbox — Processing Status</h2>
        <p className="kicker" style={{ marginTop: 6 }}>
          {isLoading
            ? "Connecting to the inbox…"
            : isOffline
              ? "Inbox unavailable — backend is offline."
              : "No videos in the inbox yet. Upload practice or game film to begin processing."}
        </p>
      </section>
    );
  }

  // Mock mode shows the legacy job-based view from sample data.
  if (mockMode || inboxItems.length === 0) {
    const sameSession = jobs.filter((j) => j.is_same_session || j.pipeline_mode === "same_session");
    const nightly = jobs.filter((j) => !j.is_same_session && j.pipeline_mode !== "same_session");

    const renderJobRow = (j: ApiJob) => (
      <div
        key={j.id}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "4px 0",
          borderBottom: "1px solid var(--line-soft, #333)",
          fontSize: "0.78rem",
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: jobStatusColor(j.status),
            flexShrink: 0,
          }}
        />
        <span style={{ flex: 1, fontWeight: 600 }}>
          {j.job_type}
          <span
            style={{
              display: "inline-block",
              padding: "1px 6px",
              borderRadius: 4,
              fontSize: "0.65rem",
              fontWeight: 700,
              background: (j.pipeline_mode === "same_session" || j.is_same_session)
                ? "oklch(0.65 0.18 145 / 0.25)"
                : "oklch(0.55 0.12 250 / 0.25)",
              color: "var(--text)",
              marginLeft: 6,
            }}
          >
            {(j.pipeline_mode === "same_session" || j.is_same_session) ? "Same-Session" : "Nightly"}
          </span>
        </span>
        <span style={{ color: jobStatusColor(j.status), fontWeight: 600, textTransform: "capitalize" }}>
          {j.status}
        </span>
      </div>
    );

    return (
      <section className="panel panel-pad span-12">
        <h2 className="panel-title">Practice Inbox — Processing Status</h2>
        <p className="kicker" style={{ marginBottom: 8 }}>
          {sameSession.length} same-session · {nightly.length} nightly
        </p>
        {jobs.length === 0 && (
          <p className="kicker">No processing jobs yet. Upload video to begin.</p>
        )}
        {sameSession.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <h3 style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent-green, #4ade80)", marginBottom: 4 }}>Same-Session (period-break)</h3>
            {sameSession.map(renderJobRow)}
          </div>
        )}
        {nightly.length > 0 && (
          <div>
            <h3 style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted, #94a3b8)", marginBottom: 4 }}>Nightly (full quality)</h3>
            {nightly.map(renderJobRow)}
          </div>
        )}
      </section>
    );
  }

  // Real backend-backed inbox view
  return (
    <section className="panel panel-pad span-12">
      <h2 className="panel-title">Practice Inbox — Processing Status</h2>
      <p className="kicker" style={{ marginBottom: 8 }}>
        {inboxItems.length} video{inboxItems.length !== 1 ? "s" : ""} in inbox
      </p>
      {inboxItems.map((item) => (
        <InboxVideoRow key={item.video_id} item={item} />
      ))}
    </section>
  );
}

function InboxVideoRow({ item }: { item: VideoInboxItem }) {
  const statusColor = (s: string) => {
    if (s === "ready") return "var(--accent-green, #4ade80)";
    if (s === "processing") return "var(--accent-amber, #fbbf24)";
    if (s === "failed") return "var(--accent-red, #f87171)";
    return "var(--text-muted, #94a3b8)";
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 0",
        borderBottom: "1px solid var(--line-soft, #333)",
        fontSize: "0.78rem",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: statusColor(item.video_status),
          flexShrink: 0,
        }}
      />
      <span style={{ flex: 1, fontWeight: 600 }}>
        {item.filename}
        {item.same_session_job_count > 0 && (
          <span style={{ display: "inline-block", padding: "1px 6px", borderRadius: 4, fontSize: "0.65rem", fontWeight: 700, background: "oklch(0.65 0.18 145 / 0.25)", color: "var(--text)", marginLeft: 6 }}>
            {item.same_session_job_count} same-session
          </span>
        )}
      </span>
      <span style={{ fontSize: "0.72rem", color: "var(--text-muted, #94a3b8)" }}>
        {item.succeeded_jobs}/{item.total_jobs} jobs
        {item.clip_count > 0 && ` · ${item.clip_count} clips`}
        {item.calibration_safe_pct !== null && ` · ${item.calibration_safe_pct}% safe`}
      </span>
      <span style={{ color: statusColor(item.video_status), fontWeight: 600, textTransform: "capitalize" }}>
        {item.video_status}
      </span>
      {item.latest_error_message && (
        <span title={item.latest_error_message} style={{ color: "var(--accent-red, #f87171)", fontSize: "0.7rem", cursor: "help" }}>
          {item.latest_error_stage ?? "Error"}
        </span>
      )}
    </div>
  );
}

// ── Recent Film ──────────────────────────────────────────────────────────────

function RecentFilmCard({ onUploadClick }: { onUploadClick: () => void }) {
  const { data, apiStatus } = useAppState();
  const videos = [...data.videos]
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
    .slice(0, 6);

  return (
    <section className="panel panel-pad span-4" data-testid="dashboard-recent-film">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <h2 className="panel-title">Recent Film</h2>
        <button className="control-button primary" onClick={onUploadClick}>
          <Upload size={15} /> Upload Film
        </button>
      </div>
      {videos.length === 0 ? (
        <p className="kicker" style={{ marginTop: 10 }}>{filmEmptyMessage(apiStatus)}</p>
      ) : (
        <div className="list-stack" style={{ marginTop: 10 }}>
          {videos.map((v) => (
            <VideoLine key={v.id} video={v} />
          ))}
        </div>
      )}
      <Link href="/film-room/?tab=browse" className="link-button" style={{ marginTop: 10, display: "inline-block" }}>
        Browse all film →
      </Link>
    </section>
  );
}

function VideoLine({ video }: { video: ApiVideo }) {
  const color = video.status === "ready"
    ? "var(--accent-green, #4ade80)"
    : video.status === "failed"
      ? "var(--accent-red, #f87171)"
      : "var(--accent-amber, #fbbf24)";
  return (
    <div className="status-row" style={{ gridTemplateColumns: "1fr auto" }}>
      <div style={{ minWidth: 0 }}>
        <strong style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {video.filename}
        </strong>
        <span className="kicker">{formatStamp(video.recorded_at ?? video.created_at)}</span>
      </div>
      <span style={{ color, fontWeight: 700, fontSize: "0.72rem", textTransform: "capitalize", alignSelf: "center" }}>
        {video.status}
      </span>
    </div>
  );
}

function filmEmptyMessage(status: ApiStatus): string {
  switch (status) {
    case "loading":
    case "idle":
      return "Loading film…";
    case "offline":
      return "Film list unavailable — backend is offline.";
    default:
      return "No film yet. Upload practice or game video to get started.";
  }
}

// ── Processing Jobs (per-stage progress) ─────────────────────────────────────

function JobsCard() {
  const { authToken } = useAppState();
  const fetcher = useCallback(() => fetchJobs({ limit: 10 }, authToken), [authToken]);
  const { state, reload } = useFetchState(fetcher);

  return (
    <section className="panel panel-pad span-4" data-testid="dashboard-jobs">
      <h2 className="panel-title">Processing Jobs</h2>
      {state.kind === "loading" && <p className="kicker" style={{ marginTop: 10 }}>Loading jobs…</p>}
      {state.kind === "offline" && (
        <p className="kicker" style={{ marginTop: 10 }}>
          Jobs unavailable — backend is offline.
        </p>
      )}
      {state.kind === "error" && (
        <div style={{ marginTop: 10 }}>
          <p className="kicker" style={{ color: "var(--accent-red, #f87171)" }}>{state.message}</p>
          <button className="control-button" style={{ marginTop: 8 }} onClick={reload}>Retry</button>
        </div>
      )}
      {state.kind === "empty" && (
        <p className="kicker" style={{ marginTop: 10 }}>
          No processing jobs yet. Upload film to start the pipeline.
        </p>
      )}
      {state.kind === "ready" && (
        <div className="list-stack" style={{ marginTop: 10 }}>
          {state.data.map((job) => (
            <JobRow key={job.id} job={job} />
          ))}
        </div>
      )}
    </section>
  );
}

function JobRow({ job }: { job: ApiJob }) {
  const stages = summarizeProgress(job.progress);
  const lease = leaseSummary(job);
  return (
    <div style={{ padding: "4px 0", borderBottom: "1px solid var(--line-soft, #333)", fontSize: "0.78rem" }} data-testid={`job-row-${job.id}`}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: jobStatusColor(job.status),
            flexShrink: 0,
          }}
        />
        <span style={{ flex: 1, fontWeight: 600 }}>{job.job_type}</span>
        <span style={{ color: jobStatusColor(job.status), fontWeight: 600, textTransform: "capitalize" }}>
          {job.status}
        </span>
      </div>
      {lease && (
        <div
          className="kicker"
          style={{ marginTop: 2 }}
          data-testid={`job-lease-${job.id}`}
        >
          {lease}
        </div>
      )}
      {stages.length > 0 && (
        <div
          className="kicker"
          style={{ marginTop: 2, display: "flex", flexWrap: "wrap", gap: "2px 10px" }}
          data-testid={`job-progress-${job.id}`}
        >
          {stages.map(({ stage, status }) => (
            <span key={stage} style={{ whiteSpace: "nowrap" }}>
              {stage}{" "}
              <span style={{ color: STAGE_COLOR[status], fontWeight: 700 }} aria-label={`${stage}: ${status}`}>
                {STAGE_GLYPH[status]}
              </span>
            </span>
          ))}
        </div>
      )}
      {job.status === "failed" && job.error_message && (
        <div className="kicker" style={{ color: "var(--accent-red, #f87171)", marginTop: 2 }}>
          {job.error_stage ? `${job.error_stage}: ` : ""}{job.error_message}
        </div>
      )}
    </div>
  );
}

/**
 * One-line lease/attempt summary for a job row (queue bookkeeping from the
 * backend JobResponse). Running jobs surface a retry attempt ("attempt 2")
 * and the worker holding the lease; failed jobs say how many attempts were
 * burned. Returns null when there is nothing noteworthy to show.
 */
export function leaseSummary(
  job: Pick<ApiJob, "status" | "attempt_count" | "leased_by">,
): string | null {
  const attempts = job.attempt_count ?? 0;
  if (job.status === "running") {
    const parts: string[] = [];
    if (attempts > 1) parts.push(`attempt ${attempts}`);
    if (job.leased_by) parts.push(`worker ${job.leased_by}`);
    return parts.length > 0 ? parts.join(" · ") : null;
  }
  if (job.status === "failed" && attempts >= 1) {
    return `failed after ${attempts} attempt${attempts === 1 ? "" : "s"}`;
  }
  return null;
}

type StageStatus = "done" | "running" | "failed" | "skipped" | "pending";

const STAGE_GLYPH: Record<StageStatus, string> = {
  done: "✓",
  running: "●",
  failed: "✕",
  skipped: "–",
  pending: "○",
};

const STAGE_COLOR: Record<StageStatus, string> = {
  done: "var(--accent-green, #4ade80)",
  running: "var(--accent-amber, #fbbf24)",
  failed: "var(--accent-red, #f87171)",
  skipped: "var(--text-muted, #94a3b8)",
  pending: "var(--text-muted, #94a3b8)",
};

/**
 * Collapse a job's per-stage progress map into an ordered stage summary.
 * Clip-suffixed keys (`"track:1a2b3c4d"`) fold into their base stage; a stage
 * is running while any of its entries is `started`, failed if any failed,
 * done when everything succeeded (or was skipped).
 */
export function summarizeProgress(
  progress: Record<string, JobStageProgress> | null | undefined,
): Array<{ stage: string; status: StageStatus }> {
  if (!progress) return [];
  const order: string[] = [];
  const byStage = new Map<string, string[]>();
  for (const [key, value] of Object.entries(progress)) {
    const stage = key.split(":")[0];
    if (!byStage.has(stage)) {
      byStage.set(stage, []);
      order.push(stage);
    }
    byStage.get(stage)!.push(String(value?.status ?? ""));
  }
  return order.map((stage) => {
    const statuses = byStage.get(stage)!;
    let status: StageStatus;
    if (statuses.includes("failed")) status = "failed";
    else if (statuses.includes("started")) status = "running";
    else if (statuses.every((s) => s === "skipped")) status = "skipped";
    else if (statuses.every((s) => s === "succeeded" || s === "skipped")) status = "done";
    else status = "pending";
    return { stage, status };
  });
}

function jobStatusColor(s: string): string {
  if (s === "succeeded") return "var(--accent-green, #4ade80)";
  if (s === "running") return "var(--accent-amber, #fbbf24)";
  if (s === "failed") return "var(--accent-red, #f87171)";
  return "var(--text-muted, #94a3b8)";
}

// ── Coaching Alerts summary ──────────────────────────────────────────────────

function AlertsSummaryCard() {
  const { authToken } = useAppState();
  const fetcher = useCallback(() => fetchAlerts({ limit: 5 }, authToken), [authToken]);
  const { state, reload } = useFetchState(fetcher);

  return (
    <section className="panel panel-pad span-4" data-testid="dashboard-alerts">
      <h2 className="panel-title">Coaching Alerts</h2>
      {state.kind === "loading" && <p className="kicker" style={{ marginTop: 10 }}>Loading alerts…</p>}
      {state.kind === "offline" && (
        <p className="kicker" style={{ marginTop: 10 }}>
          Alerts unavailable — backend is offline.
        </p>
      )}
      {state.kind === "error" && (
        <div style={{ marginTop: 10 }}>
          <p className="kicker" style={{ color: "var(--accent-red, #f87171)" }}>{state.message}</p>
          <button className="control-button" style={{ marginTop: 8 }} onClick={reload}>Retry</button>
        </div>
      )}
      {state.kind === "empty" && (
        <p className="kicker" style={{ marginTop: 10 }}>
          No alerts generated yet. They appear as the pipeline processes film.
        </p>
      )}
      {state.kind === "ready" && (
        <div className="list-stack" style={{ marginTop: 10, gap: 6 }}>
          {state.data.map((a) => (
            <AlertLine key={a.id} alert={a} />
          ))}
        </div>
      )}
      <Link href="/alerts" className="link-button" style={{ marginTop: 10, display: "inline-block" }}>
        Open alerts inbox →
      </Link>
    </section>
  );
}

function AlertLine({ alert }: { alert: ApiAlert }) {
  const pill = alert.severity === "high" || alert.severity === "critical"
    ? "danger"
    : alert.severity === "medium" || alert.severity === "warning"
      ? "warning"
      : "info";
  return (
    <div className="status-row" style={{ gridTemplateColumns: "1fr auto" }}>
      <div style={{ minWidth: 0 }}>
        <strong>{alert.alert_type}</strong>
        <div className="kicker">
          {alert.position_group} · {alert.metric_name} · {Math.round(alert.confidence * 100)}%
        </div>
      </div>
      <span className={`status-pill ${pill}`} style={{ alignSelf: "center" }}>{alert.severity}</span>
    </div>
  );
}

function formatStamp(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return value;
  }
}
