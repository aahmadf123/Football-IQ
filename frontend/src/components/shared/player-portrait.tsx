/**
 * Jersey-number identity card for a player (no photo pipeline yet — renders
 * the real jersey/position/name from the roster).
 */

import type { PlayerSummary } from "@/lib/types";

export function PlayerPortrait({ player, compact = false }: { player: PlayerSummary; compact?: boolean }) {
  return (
    <div
      style={{
        minHeight: compact ? 84 : 124,
        borderRadius: 7,
        border: "1px solid var(--line-soft)",
        background: "linear-gradient(135deg, oklch(0.2 0.05 252), oklch(0.33 0.09 252))",
        padding: compact ? 10 : 14,
        display: "grid",
        alignContent: "end",
      }}
    >
      <strong style={{ fontSize: compact ? "1.45rem" : "2.1rem", lineHeight: 1 }}>#{player.jersey}</strong>
      <span style={{ color: "var(--muted)", fontWeight: 800, fontSize: compact ? "0.78rem" : undefined }}>{player.position} · {player.name}</span>
    </div>
  );
}
