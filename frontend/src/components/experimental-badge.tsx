"use client";

/**
 * Badge that marks a surface as EXPERIMENTAL (Issue #10). Frontier analytics
 * (xSep/xYards/xPressure) and in-game pattern breaks are derived from tracking
 * outputs that are not yet validated for Toledo — this badge makes sure a coach
 * never mistakes them for a trusted result.
 */
export function ExperimentalBadge({ label = "Experimental" }: { label?: string }) {
  return (
    <span
      className="experimental-badge"
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: 999,
        background: "var(--accent-amber, #fbbf24)",
        color: "#1a1a1a",
        fontSize: "0.7rem",
        fontWeight: 700,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        marginLeft: 8,
      }}
      aria-label="Experimental metric — not a validated result"
      data-testid="experimental-badge"
    >
      {label}
    </span>
  );
}
