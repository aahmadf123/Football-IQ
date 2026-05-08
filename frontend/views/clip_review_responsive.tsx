"use client";

/**
 * ClipReviewResponsive — touch-optimized clip review component.
 *
 * Targets:
 *   - Laptop (≥1024 px): side-by-side video + metadata panel
 *   - iPad (768–1023 px): stacked layout, large tap targets
 *   - Mobile fallback (<768 px): single-column, swipe-to-next
 *
 * Features:
 *   - HLS video playback via native <video> (falls back to MP4 period overlay)
 *   - Touch swipe left/right to navigate between clips
 *   - Tap-to-approve / tap-to-flag one-tap corrections
 *   - Real-time processing status badge (polling /api/v1/jobs)
 *   - "Period overlay" badge for same-session clips pending full HLS render
 */

import { useCallback, useEffect, useRef, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ClipMeta {
  id: string;
  videoId: string;
  playNumber?: number;
  startTime: number;
  endTime: number;
  /** R2 URI of the full-resolution HLS master playlist (nightly). */
  hlsMasterUri?: string;
  /** R2 URI of the period-break reduced-resolution MP4 overlay. */
  periodOverlayUri?: string;
  /** Signed playback URL — resolved from hlsMasterUri or periodOverlayUri. */
  playbackUrl?: string;
  formation?: string;
  defensiveFront?: string;
  direction?: string;
  analyticsSafe?: boolean;
  isSameSession?: boolean;
  processingJobId?: string;
}

export type ReviewAction = "approve" | "flag" | "reject";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface ClipReviewResponsiveProps {
  /** Ordered list of clips to review. */
  clips: ClipMeta[];
  /** Called when the user approves / flags / rejects a clip. */
  onAction?: (clipId: string, action: ReviewAction) => void;
  /** API base URL (e.g. "https://api.football-iq.app") */
  apiBaseUrl?: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const JOB_POLL_MS = 5_000;

// ── Component ─────────────────────────────────────────────────────────────────

export default function ClipReviewResponsive({
  clips,
  onAction,
  apiBaseUrl = API_BASE,
}: ClipReviewResponsiveProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Touch-swipe state
  const touchStartX = useRef<number>(0);
  const touchStartY = useRef<number>(0);

  const clip = clips[activeIndex];

  // ── Job status polling ─────────────────────────────────────────────────────

  useEffect(() => {
    if (!clip?.processingJobId || !apiBaseUrl) return;

    setJobStatus(null);
    let cancelled = false;

    const poll = async () => {
      while (!cancelled) {
        try {
          const res = await fetch(
            `${apiBaseUrl}/api/v1/jobs/${clip.processingJobId}`,
          );
          if (res.ok) {
            const data = (await res.json()) as { status: JobStatus };
            if (!cancelled) setJobStatus(data.status);
            if (
              data.status === "succeeded" ||
              data.status === "failed"
            ) {
              break;
            }
          }
        } catch {
          // network error — keep polling
        }
        if (cancelled) break;
        await new Promise<void>((resolve) => setTimeout(resolve, JOB_POLL_MS));
      }
    };

    void poll();
    return () => {
      cancelled = true;
    };
  }, [clip?.processingJobId, apiBaseUrl]);

  // ── Video source ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!videoRef.current || !clip) return;
    const src = clip.playbackUrl ?? clip.periodOverlayUri ?? "";
    if (src && videoRef.current.src !== src) {
      videoRef.current.src = src;
      videoRef.current.load();
    }
  }, [clip]);

  // ── Navigation ─────────────────────────────────────────────────────────────

  const goTo = useCallback(
    (index: number) => {
      const clamped = Math.max(0, Math.min(clips.length - 1, index));
      setActiveIndex(clamped);
    },
    [clips.length],
  );

  const goPrev = useCallback(() => goTo(activeIndex - 1), [activeIndex, goTo]);
  const goNext = useCallback(() => goTo(activeIndex + 1), [activeIndex, goTo]);

  // ── Touch handlers ─────────────────────────────────────────────────────────

  const onTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    const dx = e.changedTouches[0].clientX - touchStartX.current;
    const dy = e.changedTouches[0].clientY - touchStartY.current;
    // Only treat primarily horizontal swipes as navigation
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 40) {
      if (dx < 0) goNext();
      else goPrev();
    }
  };

  // ── Action handler ─────────────────────────────────────────────────────────

  const handleAction = (action: ReviewAction) => {
    if (!clip) return;
    onAction?.(clip.id, action);
  };

  if (clips.length === 0) {
    return (
      <div style={styles.empty}>
        <p>No clips available for review.</p>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div
      style={styles.root}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      {/* ── Header ── */}
      <div style={styles.header}>
        <span style={styles.headerTitle}>Clip Review</span>
        <span style={styles.headerCounter}>
          {activeIndex + 1} / {clips.length}
        </span>
      </div>

      {/* ── Main layout ── */}
      <div style={styles.mainLayout}>
        {/* Video panel */}
        <div style={styles.videoPanel}>
          <div style={styles.videoWrapper}>
            <video
              ref={videoRef}
              controls
              playsInline
              style={styles.video}
              aria-label={`Clip ${clip.playNumber ?? activeIndex + 1} video`}
            />
          </div>

          {/* Badges */}
          <div style={styles.badgeRow}>
            {clip.isSameSession && (
              <span style={{ ...styles.badge, ...styles.badgeSameSession }}>
                Period overlay
              </span>
            )}
            {!clip.analyticsSafe && (
              <span style={{ ...styles.badge, ...styles.badgeWarning }}>
                Calibration warning
              </span>
            )}
            {jobStatus && jobStatus !== "succeeded" && (
              <span style={{ ...styles.badge, ...styles.badgeJob }}>
                Job: {jobStatus}
              </span>
            )}
          </div>

          {/* Navigation (touch-friendly large targets) */}
          <div style={styles.navRow}>
            <button
              onClick={goPrev}
              disabled={activeIndex === 0}
              style={styles.navBtn}
              aria-label="Previous clip"
            >
              ‹ Prev
            </button>
            <button
              onClick={goNext}
              disabled={activeIndex === clips.length - 1}
              style={styles.navBtn}
              aria-label="Next clip"
            >
              Next ›
            </button>
          </div>
        </div>

        {/* Metadata + action panel */}
        <div style={styles.metaPanel}>
          <h2 style={styles.clipTitle}>
            {clip.playNumber != null
              ? `Play #${clip.playNumber}`
              : `Clip ${activeIndex + 1}`}
          </h2>

          <dl style={styles.dl}>
            <MetaRow label="Formation" value={clip.formation} />
            <MetaRow label="Def front" value={clip.defensiveFront} />
            <MetaRow label="Direction" value={clip.direction} />
            <MetaRow
              label="Duration"
              value={`${(clip.endTime - clip.startTime).toFixed(1)} s`}
            />
          </dl>

          {/* One-tap action buttons */}
          <div style={styles.actionRow}>
            <ActionButton
              label="✓ Approve"
              color="#16a34a"
              onClick={() => handleAction("approve")}
            />
            <ActionButton
              label="⚑ Flag"
              color="#ca8a04"
              onClick={() => handleAction("flag")}
            />
            <ActionButton
              label="✕ Reject"
              color="#dc2626"
              onClick={() => handleAction("reject")}
            />
          </div>
        </div>
      </div>

      {/* ── Thumbnail strip ── */}
      <div style={styles.strip} role="list" aria-label="Clip thumbnails">
        {clips.map((c, i) => (
          <button
            key={c.id}
            onClick={() => goTo(i)}
            style={{
              ...styles.stripItem,
              ...(i === activeIndex ? styles.stripItemActive : {}),
            }}
            role="listitem"
            aria-label={`Go to clip ${i + 1}`}
            aria-current={i === activeIndex}
          >
            {c.playNumber ?? i + 1}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MetaRow({
  label,
  value,
}: {
  label: string;
  value?: string | number;
}) {
  if (value == null) return null;
  return (
    <>
      <dt style={styles.dt}>{label}</dt>
      <dd style={styles.dd}>{value}</dd>
    </>
  );
}

function ActionButton({
  label,
  color,
  onClick,
}: {
  label: string;
  color: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{ ...styles.actionBtn, backgroundColor: color }}
    >
      {label}
    </button>
  );
}

// ── Inline styles (no CSS dependency) ────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    fontFamily: "system-ui, sans-serif",
    background: "#0f172a",
    color: "#f1f5f9",
    userSelect: "none",
    WebkitUserSelect: "none",
  },
  empty: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    color: "#94a3b8",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 16px",
    background: "#1e293b",
    borderBottom: "1px solid #334155",
    flexShrink: 0,
  },
  headerTitle: { fontWeight: 700, fontSize: 16 },
  headerCounter: { fontSize: 13, color: "#94a3b8" },
  mainLayout: {
    display: "flex",
    flex: 1,
    flexWrap: "wrap",
    overflow: "hidden",
  },
  videoPanel: {
    flex: "1 1 480px",
    display: "flex",
    flexDirection: "column",
    padding: 12,
    gap: 8,
  },
  videoWrapper: {
    flex: 1,
    background: "#000",
    borderRadius: 8,
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 180,
  },
  video: {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    display: "block",
  },
  badgeRow: { display: "flex", gap: 6, flexWrap: "wrap" },
  badge: {
    padding: "3px 8px",
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 0.3,
  },
  badgeSameSession: { background: "#1d4ed8", color: "#fff" },
  badgeWarning: { background: "#92400e", color: "#fef3c7" },
  badgeJob: { background: "#374151", color: "#d1d5db" },
  navRow: {
    display: "flex",
    gap: 8,
    justifyContent: "space-between",
  },
  navBtn: {
    flex: 1,
    padding: "12px 0",
    background: "#1e293b",
    color: "#f1f5f9",
    border: "1px solid #334155",
    borderRadius: 6,
    fontSize: 15,
    cursor: "pointer",
    minHeight: 44, // WCAG touch target
  },
  metaPanel: {
    flex: "0 0 280px",
    display: "flex",
    flexDirection: "column",
    padding: "16px 16px 12px",
    background: "#1e293b",
    borderLeft: "1px solid #334155",
    gap: 12,
    overflowY: "auto",
  },
  clipTitle: { margin: 0, fontSize: 17, fontWeight: 700 },
  dl: {
    display: "grid",
    gridTemplateColumns: "auto 1fr",
    gap: "4px 12px",
    margin: 0,
  },
  dt: { color: "#94a3b8", fontSize: 12, fontWeight: 500, alignSelf: "center" },
  dd: { margin: 0, fontSize: 14, color: "#f1f5f9" },
  actionRow: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    marginTop: "auto",
  },
  actionBtn: {
    padding: "14px 0",
    border: "none",
    borderRadius: 8,
    color: "#fff",
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
    minHeight: 44, // WCAG touch target
    letterSpacing: 0.2,
  },
  strip: {
    display: "flex",
    overflowX: "auto",
    gap: 6,
    padding: "8px 12px",
    background: "#1e293b",
    borderTop: "1px solid #334155",
    flexShrink: 0,
    WebkitOverflowScrolling: "touch",
  },
  stripItem: {
    minWidth: 36,
    height: 36,
    background: "#334155",
    border: "none",
    borderRadius: 6,
    color: "#cbd5e1",
    fontSize: 12,
    cursor: "pointer",
    flexShrink: 0,
  },
  stripItemActive: {
    background: "#2563eb",
    color: "#fff",
    fontWeight: 700,
  },
};
