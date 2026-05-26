"use client";

import type { ApiStatus } from "@/lib/app-state";

interface Props {
  status: ApiStatus;
}

export function MockBadge({ status }: Props) {
  if (status === "live" || status === "idle" || status === "loading") return null;

  const label = status === "mock" ? "Mock data" : "API offline";
  const background = status === "mock" ? "var(--gold)" : "#a33";
  const color = status === "mock" ? "#1a1a1a" : "#fff";

  return (
    <span
      className="mock-badge"
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: 999,
        background,
        color,
        fontSize: "0.7rem",
        fontWeight: 700,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        marginLeft: 8,
      }}
      aria-label={`Data source: ${label}`}
      data-testid="mock-badge"
    >
      {label}
    </span>
  );
}
