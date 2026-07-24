"use client";

/**
 * Shared analytics card state model (Issue #106).
 *
 * Every analytics surface in the app — dashboard tiles, the Analytics page,
 * the scout views — should render through this component so that
 * "live / loading / processing / gated / unavailable / error" are presented
 * consistently and so future metrics can plug in without re-implementing
 * gating logic.
 *
 * The model is intentionally explicit: we never want to render a hardcoded
 * number "as if" it were live. A card whose metric isn't wired yet should be
 * ``{ kind: "unavailable" }`` (or ``{ kind: "gated" }`` if it depends on a
 * plan/role), not a fabricated value.
 */

import type { ReactNode } from "react";

export type AnalyticsCardState =
  /** Real backend data; render ``children``. */
  | { kind: "live"; updatedAt?: string | null }
  /** Request in flight or initial mount before the fetch resolves. */
  | { kind: "loading"; label?: string }
  /** The metric is queued/computing on the backend. */
  | { kind: "processing"; label?: string; etaSeconds?: number }
  /** The metric is implemented but not visible to this user/plan/role. */
  | { kind: "gated"; reason: string }
  /** The metric is not implemented yet, or has no data for these filters. */
  | { kind: "unavailable"; reason: string }
  /** Backend reachable but the response had no data. */
  | { kind: "empty"; reason: string }
  /** Request failed (network/5xx). */
  | { kind: "error"; message: string; onRetry?: () => void };

interface Props {
  title: string;
  state: AnalyticsCardState;
  /** Rendered only when ``state.kind === "live"``. */
  children?: ReactNode;
  /** Optional className on the outer ``<section>``. */
  className?: string;
  /** Optional inline style on the outer ``<section>``. */
  style?: React.CSSProperties;
  /** Optional element rendered to the right of the title (icon, link, etc). */
  headerExtra?: ReactNode;
  /**
   * Optional coach-readable sentence explaining *why* the metric is gated for
   * this specific footage (e.g. the calibration reason from the overlays
   * payload). Rendered only when ``state.kind === "gated"``, under the
   * generic gating reason.
   */
  gatedReason?: string;
}

export function AnalyticsCard({
  title,
  state,
  children,
  className,
  style,
  headerExtra,
  gatedReason,
}: Props) {
  return (
    <section
      className={`panel panel-pad ${className ?? ""}`.trim()}
      style={style}
      data-testid={`analytics-card-${slug(title)}`}
      data-card-state={state.kind}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
        }}
      >
        <h2 className="panel-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {title}
          <StateBadge state={state} />
        </h2>
        {headerExtra}
      </div>
      <div style={{ marginTop: 12 }}>
        {state.kind === "live" && children}
        {state.kind === "loading" && (
          <p className="kicker" data-testid="card-loading">
            {state.label ?? "Loading…"}
          </p>
        )}
        {state.kind === "processing" && (
          <p className="kicker" data-testid="card-processing">
            {state.label ?? "Processing… results will appear when the job completes."}
            {state.etaSeconds != null ? ` (~${state.etaSeconds}s)` : ""}
          </p>
        )}
        {state.kind === "empty" && (
          <p className="kicker" data-testid="card-empty">
            {state.reason}
          </p>
        )}
        {state.kind === "unavailable" && (
          <p className="kicker" data-testid="card-unavailable">
            {state.reason}
          </p>
        )}
        {state.kind === "gated" && (
          <div data-testid="card-gated">
            <p className="kicker">{state.reason}</p>
            {gatedReason && (
              <p
                className="kicker"
                data-testid="card-gated-reason"
                style={{ marginTop: 6, color: "var(--text)" }}
              >
                {gatedReason}
              </p>
            )}
          </div>
        )}
        {state.kind === "error" && (
          <div data-testid="card-error">
            <p
              className="kicker"
              style={{ color: "var(--accent-red, #f87171)" }}
            >
              {state.message}
            </p>
            {state.onRetry && (
              <button
                type="button"
                className="control-button"
                style={{ marginTop: 8 }}
                onClick={state.onRetry}
              >
                Retry
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function StateBadge({ state }: { state: AnalyticsCardState }) {
  const meta = badgeMeta(state.kind);
  if (!meta) return null;
  return (
    <span
      style={{
        fontSize: "0.62rem",
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        padding: "2px 6px",
        borderRadius: 4,
        background: meta.background,
        color: meta.color,
      }}
      data-testid={`card-badge-${state.kind}`}
    >
      {meta.label}
    </span>
  );
}

function badgeMeta(kind: AnalyticsCardState["kind"]):
  | { label: string; background: string; color: string }
  | null {
  switch (kind) {
    case "live":
      return null;
    case "loading":
      return { label: "Loading", background: "oklch(0.55 0.12 250 / 0.25)", color: "var(--text)" };
    case "processing":
      return { label: "Processing", background: "oklch(0.65 0.18 80 / 0.30)", color: "var(--text)" };
    case "gated":
      return { label: "Locked", background: "oklch(0.45 0.05 252 / 0.55)", color: "var(--text)" };
    case "unavailable":
      return { label: "Not yet", background: "oklch(0.32 0.04 252 / 0.65)", color: "var(--muted)" };
    case "empty":
      return { label: "Empty", background: "oklch(0.32 0.04 252 / 0.65)", color: "var(--muted)" };
    case "error":
      return { label: "Error", background: "oklch(0.35 0.18 25 / 0.45)", color: "#fff" };
  }
}

function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}
