"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FootballShell } from "@/components/football-shell";
import { AnalyticsCard, type AnalyticsCardState } from "@/components/analytics-card";
import { useAppState } from "@/lib/app-state";
import {
  fetchAlerts,
  fetchSelfScoutTendencies,
  fetchVideos,
  type ApiAlert,
} from "@/lib/api";
import type { ApiVideo, SelfScoutResponse, TendencyEntry } from "@/lib/types";

type FetchState<T> =
  | { kind: "loading" }
  | { kind: "offline" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; data: T };

export default function AnalyticsPage() {
  return (
    <FootballShell activePage="analytics">
      <AnalyticsView />
    </FootballShell>
  );
}

function AnalyticsView() {
  const { authToken, selectedDate, sessionType } = useAppState();
  const [videos, setVideos] = useState<FetchState<ApiVideo[]>>({ kind: "loading" });
  const [scout, setScout] = useState<FetchState<SelfScoutResponse>>({ kind: "loading" });
  const [alerts, setAlerts] = useState<FetchState<ApiAlert[]>>({ kind: "loading" });

  const loadVideos = useCallback(async () => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setVideos({ kind: "offline" });
      return;
    }
    setVideos({ kind: "loading" });
    try {
      const filters: Record<string, string | number> = { limit: 200 };
      if (selectedDate) {
        filters.recorded_after = `${selectedDate}T00:00:00Z`;
        filters.recorded_before = `${selectedDate}T23:59:59.999999Z`;
      }
      if (sessionType !== "all") {
        filters.session_kind = sessionType;
      }
      const list = await fetchVideos(filters, authToken);
      setVideos(list.length === 0 ? { kind: "empty" } : { kind: "ready", data: list });
    } catch (err) {
      setVideos({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, [authToken, selectedDate, sessionType]);

  const loadScout = useCallback(async () => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setScout({ kind: "offline" });
      return;
    }
    setScout({ kind: "loading" });
    try {
      const data = await fetchSelfScoutTendencies(null, authToken);
      setScout(
        data.clip_count === 0
          ? { kind: "empty" }
          : { kind: "ready", data },
      );
    } catch (err) {
      setScout({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, [authToken]);

  const loadAlerts = useCallback(async () => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setAlerts({ kind: "offline" });
      return;
    }
    setAlerts({ kind: "loading" });
    try {
      const list = await fetchAlerts({ limit: 25 }, authToken);
      setAlerts(list.length === 0 ? { kind: "empty" } : { kind: "ready", data: list });
    } catch (err) {
      setAlerts({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, [authToken]);

  useEffect(() => {
    loadVideos();
  }, [loadVideos]);

  useEffect(() => {
    loadScout();
  }, [loadScout]);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  const totalPlaysState = useMemo<AnalyticsCardState>(() => {
    switch (videos.kind) {
      case "loading":
        return { kind: "loading" };
      case "offline":
        return {
          kind: "unavailable",
          reason: "Backend offline — set NEXT_PUBLIC_API_URL to compute live metrics.",
        };
      case "error":
        return { kind: "error", message: videos.message, onRetry: loadVideos };
      case "empty":
        return {
          kind: "empty",
          reason: "No videos uploaded for the selected date / session yet.",
        };
      case "ready":
        return { kind: "live" };
    }
  }, [videos, loadVideos]);

  const scoutCardState = scoutToCardState(scout, loadScout);
  const alertsCardState = alertsToCardState(alerts, loadAlerts);

  return (
    <div className="content-grid">
      <AnalyticsCard
        title="Film Volume"
        state={totalPlaysState}
        className="span-4"
      >
        {videos.kind === "ready" && (
          <div className="metric-grid" style={{ marginTop: 4 }}>
            <Metric label="Videos" value={String(videos.data.length)} />
            <Metric
              label="Ready"
              value={String(videos.data.filter((v) => v.status === "ready").length)}
            />
            <Metric
              label="Processing"
              value={String(videos.data.filter((v) => v.status === "processing").length)}
            />
          </div>
        )}
      </AnalyticsCard>

      <AnalyticsCard
        title="Expected Separation (xSep)"
        state={{
          kind: "unavailable",
          reason:
            "xSep requires the receiver-tracking metrics pipeline. Tracked in Issue #10 — gated until a live model lands.",
        }}
        className="span-4"
      />

      <AnalyticsCard
        title="Expected Yards (xYards)"
        state={{
          kind: "unavailable",
          reason:
            "xYards requires the play-outcome metrics pipeline. Tracked in Issue #10 — gated until a live model lands.",
        }}
        className="span-4"
      />

      <AnalyticsCard
        title="Expected Pressure (xPressure)"
        state={{
          kind: "unavailable",
          reason:
            "xPressure requires the pass-rush metrics pipeline. Tracked in Issue #10 — gated until a live model lands.",
        }}
        className="span-4"
      />

      <AnalyticsCard
        title="Model Quality"
        state={{
          kind: "gated",
          reason:
            "Boundary / tracking / label / pose quality scores are sourced from the model registry. Not exposed to coaches in P1.",
        }}
        className="span-4"
      />

      <AnalyticsCard
        title="Spatial Heatmap"
        state={{
          kind: "unavailable",
          reason:
            "Spatial heatmaps require aggregated tracklet positions across many clips. Gated until the metrics pipeline backfills.",
        }}
        className="span-4"
      />

      <AnalyticsCard
        title="Formation Run / Pass"
        state={scoutCardState}
        className="span-6"
      >
        {scout.kind === "ready" && (
          <TendencyTable entries={scout.data.formation_tendencies} />
        )}
      </AnalyticsCard>

      <AnalyticsCard
        title="Coaching Alerts"
        state={alertsCardState}
        className="span-6"
      >
        {alerts.kind === "ready" && (
          <div className="list-stack" style={{ gap: 6 }}>
            {alerts.data.slice(0, 6).map((a) => (
              <div
                key={a.id}
                className="status-row"
                style={{ gridTemplateColumns: "1fr auto" }}
                data-testid={`analytics-alert-${a.id}`}
              >
                <div>
                  <strong>{a.alert_type}</strong>
                  <div className="kicker">
                    {a.position_group} · {a.metric_name} · {Math.round(a.confidence * 100)}%
                  </div>
                </div>
                <span
                  className={`status-pill ${alertPillClass(a.severity)}`}
                >
                  {a.severity}
                </span>
              </div>
            ))}
          </div>
        )}
      </AnalyticsCard>
    </div>
  );
}

function scoutToCardState(
  scout: FetchState<SelfScoutResponse>,
  retry: () => void,
): AnalyticsCardState {
  switch (scout.kind) {
    case "loading":
      return { kind: "loading", label: "Computing tendencies…" };
    case "offline":
      return {
        kind: "unavailable",
        reason: "Backend offline — set NEXT_PUBLIC_API_URL to compute live metrics.",
      };
    case "error":
      return { kind: "error", message: scout.message, onRetry: retry };
    case "empty":
      return {
        kind: "empty",
        reason:
          "No labeled plays available yet. Upload film or wait for the labeling pipeline.",
      };
    case "ready":
      return { kind: "live" };
  }
}

function alertsToCardState(
  alerts: FetchState<ApiAlert[]>,
  retry: () => void,
): AnalyticsCardState {
  switch (alerts.kind) {
    case "loading":
      return { kind: "loading", label: "Loading alerts…" };
    case "offline":
      return {
        kind: "unavailable",
        reason: "Backend offline — set NEXT_PUBLIC_API_URL to stream alerts.",
      };
    case "error":
      return { kind: "error", message: alerts.message, onRetry: retry };
    case "empty":
      return {
        kind: "empty",
        reason: "No alerts have been generated yet for your position group.",
      };
    case "ready":
      return { kind: "live" };
  }
}

function alertPillClass(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical":
    case "high":
      return "danger";
    case "warning":
    case "medium":
      return "warning";
    default:
      return "info";
  }
}

function TendencyTable({ entries }: { entries: TendencyEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="kicker">No tendencies above the minimum-sample threshold.</p>
    );
  }
  return (
    <div className="list-stack" style={{ gap: 4 }}>
      {entries.map((e) => (
        <div
          key={e.grouping_key}
          className="status-row"
          style={{ gridTemplateColumns: "1fr 56px minmax(90px, 1fr)" }}
        >
          <strong>{e.grouping_key}</strong>
          <span>{e.total_plays}</span>
          <div className="progress">
            <i style={{ "--value": `${Math.round(e.run_rate * 100)}%` } as React.CSSProperties} />
          </div>
        </div>
      ))}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
