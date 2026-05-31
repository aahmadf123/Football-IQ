"use client";

/**
 * Same-session result-state badges (Issue #147).
 *
 * A coach reviewing a clip needs to know two things at a glance:
 *   1. Is this a *preliminary* first pass from the 90-second same-session loop,
 *      or the nightly *final* result? — the "Preliminary" pill.
 *   2. Where does it sit in the review queue? — reviewed / low-confidence /
 *      needs-review.
 *
 * Both are derived on the backend (``is_preliminary`` / ``review_state`` on the
 * clip payload) so the UI never recomputes confidence policy. The pills mirror
 * the ExperimentalBadge styling so they read as the same family of status chips.
 */
import type { ClipReviewState } from "@/lib/types";

const PILL_BASE: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "2px 8px",
  borderRadius: 999,
  fontSize: "0.7rem",
  fontWeight: 700,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

export function PreliminaryBadge() {
  return (
    <span
      className="preliminary-badge"
      style={{ ...PILL_BASE, background: "var(--accent-amber, #fbbf24)", color: "#1a1a1a" }}
      aria-label="Preliminary result — same-session first pass, not yet upgraded by nightly processing"
      data-testid="preliminary-badge"
    >
      Preliminary
    </span>
  );
}

const REVIEW_META: Record<
  ClipReviewState,
  { label: string; bg: string; fg: string; aria: string }
> = {
  reviewed: {
    label: "Reviewed",
    bg: "var(--accent-green, #4ade80)",
    fg: "#0a1f12",
    aria: "Reviewed — a coach has signed off on this clip",
  },
  low_confidence: {
    label: "Low confidence",
    bg: "var(--accent-red, #f87171)",
    fg: "#1a1a1a",
    aria: "Low confidence — review this clip before trusting its labels",
  },
  needs_review: {
    label: "Needs review",
    bg: "rgba(148,163,184,0.4)",
    fg: "var(--text, #e2e8f0)",
    aria: "Needs review — a first-pass result nobody has confirmed yet",
  },
};

export function ReviewStateBadge({ state }: { state: ClipReviewState }) {
  const meta = REVIEW_META[state];
  return (
    <span
      className="review-state-badge"
      style={{ ...PILL_BASE, background: meta.bg, color: meta.fg }}
      aria-label={meta.aria}
      data-testid={`review-state-${state}`}
    >
      {meta.label}
    </span>
  );
}

/** Convenience: render the preliminary + review pills for a clip together. */
export function ClipStateBadges({
  isPreliminary,
  reviewState,
}: {
  isPreliminary?: boolean;
  reviewState?: ClipReviewState;
}) {
  if (!isPreliminary && !reviewState) return null;
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
      {isPreliminary && <PreliminaryBadge />}
      {reviewState && <ReviewStateBadge state={reviewState} />}
    </span>
  );
}
