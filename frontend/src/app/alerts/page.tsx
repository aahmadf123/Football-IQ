"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { FootballShell } from "@/components/football-shell";
import { useAppState } from "@/lib/app-state";
import {
  actionAlert,
  fetchAlerts,
  subscribeAlerts,
  type AlertStreamHandle,
  type ApiAlert,
} from "@/lib/api";
import { ExperimentalBadge } from "@/components/experimental-badge";

type AlertsState =
  | { kind: "loading" }
  | { kind: "offline" }
  | { kind: "error"; message: string }
  | { kind: "ready"; alerts: ApiAlert[] };

type StreamState = "idle" | "connecting" | "connected" | "degraded" | "polling";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "var(--accent-red, #f87171)",
  high: "var(--accent-red, #f87171)",
  warning: "var(--accent-amber, #fbbf24)",
  medium: "var(--accent-amber, #fbbf24)",
  low: "var(--accent-green, #4ade80)",
  info: "var(--text-muted, #94a3b8)",
};

export default function AlertsPage() {
  return (
    <FootballShell activePage="alerts">
      <AlertsView />
    </FootballShell>
  );
}

function AlertsView() {
  const { mockMode, authToken } = useAppState();
  const [state, setState] = useState<AlertsState>({ kind: "loading" });
  const [streamState, setStreamState] = useState<StreamState>("idle");
  const streamRef = useRef<AlertStreamHandle | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAlerts = useCallback(async () => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setState({ kind: "offline" });
      return;
    }
    try {
      const alerts = await fetchAlerts({ limit: 50 }, authToken);
      setState({ kind: "ready", alerts });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, [authToken]);

  const handleAction = useCallback(
    async (alertId: string) => {
      try {
        const updated = await actionAlert(alertId, authToken);
        setState((cur) => {
          if (cur.kind !== "ready") return cur;
          return {
            kind: "ready",
            alerts: cur.alerts.map((a) => (a.id === alertId ? updated : a)),
          };
        });
      } catch {
        // Surface nothing destructive on failure — the alert simply stays open.
      }
    },
    [authToken],
  );

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  // SSE subscription with fallback to polling on error.
  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl || typeof fetch === "undefined") {
      setStreamState("degraded");
      return;
    }
    setStreamState("connecting");
    let cancelled = false;
    let handle: AlertStreamHandle | null = null;

    const startPolling = () => {
      if (cancelled || pollRef.current) return;
      setStreamState("polling");
      pollRef.current = setInterval(() => {
        loadAlerts();
      }, 15_000);
    };

    try {
      handle = subscribeAlerts(
        (event) => {
          if (cancelled) return;
          if (event.type === "connected") {
            setStreamState("connected");
          } else if (event.type === "alert") {
            setState((cur) => {
              if (cur.kind !== "ready") return cur;
              // De-dup by id
              if (cur.alerts.some((a) => a.id === event.alert.id)) return cur;
              return { kind: "ready", alerts: [event.alert, ...cur.alerts] };
            });
          }
        },
        () => {
          if (cancelled) return;
          setStreamState("degraded");
          handle?.close();
          handle = null;
          startPolling();
        },
        authToken,
      );
      streamRef.current = handle;
    } catch {
      startPolling();
    }

    return () => {
      cancelled = true;
      streamRef.current?.close();
      streamRef.current = null;
      handle = null;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [loadAlerts, authToken]);

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-12">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div>
            <h2 className="panel-title">Coaching Alerts</h2>
            <p className="kicker">
              Live coaching alerts streamed from the analytics and biomechanics
              pipeline. Coach/analyst-only.
              {mockMode ? " Mock mode is on — only server-backed alerts appear here." : ""}
            </p>
          </div>
          <StreamBadge state={streamState} />
        </div>
      </section>

      {state.kind === "loading" && (
        <section className="panel panel-pad span-12">
          <p className="kicker">Loading alerts…</p>
        </section>
      )}
      {state.kind === "offline" && (
        <section className="panel panel-pad span-12">
          <h3 className="panel-title">Backend not configured</h3>
          <p className="kicker" style={{ marginTop: 8 }}>
            Alerts require <code>NEXT_PUBLIC_API_URL</code>.
          </p>
        </section>
      )}
      {state.kind === "error" && (
        <section className="panel panel-pad span-12">
          <h3 className="panel-title">Could not load alerts</h3>
          <p className="kicker" style={{ marginTop: 8, color: "var(--accent-red, #f87171)" }}>
            {state.message}
          </p>
          <button className="control-button" style={{ marginTop: 12 }} onClick={loadAlerts}>
            Retry
          </button>
        </section>
      )}
      {state.kind === "ready" && state.alerts.length === 0 && (
        <section className="panel panel-pad span-12">
          <h3 className="panel-title">No alerts</h3>
          <p className="kicker" style={{ marginTop: 8 }}>
            No coaching alerts yet for your position group. New alerts will
            stream in here automatically.
          </p>
        </section>
      )}
      {state.kind === "ready" && state.alerts.length > 0 && (
        <section className="panel panel-pad span-12">
          <div className="list-stack" style={{ gap: 8 }}>
            {state.alerts.map((a) => (
              <AlertRow key={a.id} alert={a} onAction={handleAction} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function StreamBadge({ state }: { state: StreamState }) {
  const label: Record<StreamState, string> = {
    idle: "Idle",
    connecting: "Connecting…",
    connected: "Live (SSE)",
    degraded: "Degraded",
    polling: "Polling (15s)",
  };
  const color: Record<StreamState, string> = {
    idle: "var(--text-muted, #94a3b8)",
    connecting: "var(--accent-amber, #fbbf24)",
    connected: "var(--accent-green, #4ade80)",
    degraded: "var(--accent-red, #f87171)",
    polling: "var(--accent-amber, #fbbf24)",
  };
  return (
    <span
      role="status"
      aria-label={`Alert stream ${label[state]}`}
      style={{
        padding: "4px 10px",
        borderRadius: 999,
        fontSize: "0.72rem",
        fontWeight: 700,
        background: "oklch(0.18 0.02 252 / 0.6)",
        color: color[state],
        border: `1px solid ${color[state]}`,
      }}
    >
      ● {label[state]}
    </span>
  );
}

function AlertRow({
  alert,
  onAction,
}: {
  alert: ApiAlert;
  onAction?: (alertId: string) => void;
}) {
  const color = SEVERITY_COLOR[alert.severity.toLowerCase()] ?? SEVERITY_COLOR.info;
  const isTendency = alert.alert_type === "formation_tendency";
  const mv = alert.metric_value ?? {};
  const tendencyKind = typeof mv.tendency_kind === "string" ? mv.tendency_kind : null;
  const message = typeof mv.message === "string" ? mv.message : null;
  const evidence = Array.isArray(mv.evidence_clip_ids)
    ? (mv.evidence_clip_ids as unknown[]).filter((c): c is string => typeof c === "string")
    : [];
  const title = isTendency ? "Tendency break" : alert.alert_type;

  return (
    <div
      data-testid={`alert-${alert.id}`}
      style={{
        display: "flex",
        gap: 12,
        padding: 10,
        border: "1px solid var(--line-soft, #333)",
        borderRadius: 6,
        alignItems: "flex-start",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
          marginTop: 6,
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
          <strong>{title}</strong>
          <span className="kicker" style={{ textTransform: "uppercase" }}>
            {alert.position_group} · {alert.severity}
          </span>
          {tendencyKind === "pattern_break" && <ExperimentalBadge label="Pattern break" />}
        </div>
        {isTendency && message ? (
          <p className="kicker" style={{ marginTop: 4 }}>
            {message}
          </p>
        ) : (
          <p className="kicker" style={{ marginTop: 4 }}>
            {alert.metric_name} · confidence {Math.round(alert.confidence * 100)}%
            {alert.session_id ? ` · session ${alert.session_id}` : ""}
          </p>
        )}
        {isTendency && evidence.length > 0 && (
          <p className="kicker" style={{ marginTop: 4 }}>
            Examples:{" "}
            {evidence.map((clipId, i) => (
              <span key={clipId}>
                {i > 0 ? " · " : ""}
                <Link href={`/clip-review/?clipId=${encodeURIComponent(clipId)}`}>
                  clip {i + 1}
                </Link>
              </span>
            ))}
          </p>
        )}
        <p className="kicker" style={{ marginTop: 4 }}>
          {new Date(alert.created_at).toLocaleString()}
          {alert.is_acknowledged ? " · acknowledged" : ""}
          {alert.is_actioned ? " · actioned" : ""}
        </p>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {onAction && !alert.is_actioned && (
          <button
            type="button"
            className="control-button"
            data-testid={`action-${alert.id}`}
            onClick={() => onAction(alert.id)}
          >
            Mark actioned
          </button>
        )}
        {alert.clip_id && (
          <Link
            href={`/clip-review/?clipId=${encodeURIComponent(alert.clip_id)}`}
            className="control-button"
          >
            Open clip →
          </Link>
        )}
      </div>
    </div>
  );
}
