"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FootballShell } from "@/components/football-shell";
import { AnalyticsCard, type AnalyticsCardState } from "@/components/analytics-card";
import { Metric } from "@/components/shared/metric";
import { TendencyTable } from "@/components/shared/tendency-table";
import { useAppState } from "@/lib/app-state";
import { useFetchState, type FetchState } from "@/lib/fetch-state";
import {
  fetchAlerts,
  fetchFrontierMetrics,
  fetchSelfScoutTendencies,
  fetchVideos,
  type ApiAlert,
  type FrontierMetric,
} from "@/lib/api";
import type { SelfScoutResponse } from "@/lib/types";
import { ExperimentalBadge } from "@/components/experimental-badge";

const FRONTIER_UNAVAILABLE_REASON: Record<string, string> = {
  xsep: "xSep requires calibrated receiver tracking (#127/#128/#129). No experimental samples yet for this filter.",
  xyards:
    "xYards requires the play-outcome metrics pipeline. No experimental samples yet for this filter.",
  xpressure:
    "xPressure requires pass-rush tracking + snap/throw events. No experimental samples yet for this filter.",
};

export default function AnalyticsPage() {
  return (
    <FootballShell activePage="analytics">
      <AnalyticsView />
    </FootballShell>
  );
}

function AnalyticsView() {
  const { authToken, selectedDate, sessionType } = useAppState();
  // Frontier analytics (Issue #10) — experimental, may be empty.
  const [frontier, setFrontier] = useState<FrontierMetric[] | null>(null);
  const [frontierLoading, setFrontierLoading] = useState(true);

  const videosFetcher = useCallback(() => {
    const filters: Record<string, string | number> = { limit: 200 };
    if (selectedDate) {
      filters.recorded_after = `${selectedDate}T00:00:00Z`;
      filters.recorded_before = `${selectedDate}T23:59:59.999999Z`;
    }
    if (sessionType !== "all") {
      filters.session_kind = sessionType;
    }
    return fetchVideos(filters, authToken);
  }, [authToken, selectedDate, sessionType]);
  const { state: videos, reload: loadVideos } = useFetchState(videosFetcher);

  const scoutFetcher = useCallback(
    () => fetchSelfScoutTendencies(null, authToken),
    [authToken],
  );
  const { state: scout, reload: loadScout } = useFetchState(scoutFetcher, {
    isEmpty: (data) => data.clip_count === 0,
  });

  const alertsFetcher = useCallback(
    () => fetchAlerts({ limit: 25 }, authToken),
    [authToken],
  );
  const { state: alerts, reload: loadAlerts } = useFetchState(alertsFetcher);

  const loadFrontier = useCallback(async () => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setFrontier(null);
      setFrontierLoading(false);
      return;
    }
    setFrontierLoading(true);
    try {
      const res = await fetchFrontierMetrics({ limit: 100 }, authToken);
      setFrontier(Array.isArray(res?.metrics) ? res.metrics : []);
    } catch {
      // Experimental scaffolds are expected to be absent — fall back to the
      // "unavailable" card state rather than surfacing a hard error.
      setFrontier(null);
    } finally {
      setFrontierLoading(false);
    }
  }, [authToken]);

  useEffect(() => {
    loadFrontier();
  }, [loadFrontier]);

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

      <FrontierCard
        title="Expected Separation (xSep)"
        metricName="xsep"
        valueKey="yards"
        unit="yd"
        metrics={frontier}
        loading={frontierLoading}
      />

      <FrontierCard
        title="Expected Yards (xYards)"
        metricName="xyards"
        valueKey="observed_yac_yd"
        unit="yd"
        metrics={frontier}
        loading={frontierLoading}
      />

      <FrontierCard
        title="Expected Pressure (xPressure)"
        metricName="xpressure"
        valueKey="xpressure"
        unit=""
        metrics={frontier}
        loading={frontierLoading}
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

function FrontierCard({
  title,
  metricName,
  valueKey,
  unit,
  metrics,
  loading,
}: {
  title: string;
  metricName: string;
  valueKey: string;
  unit: string;
  metrics: FrontierMetric[] | null;
  loading: boolean;
}) {
  // Only non-suppressed metrics for this name count as a real value.
  const forName = (metrics ?? []).filter(
    (m) =>
      m.metric_name.toLowerCase() === metricName &&
      m.metric_value?.suppressed !== true,
  );
  const latest = forName[0];
  const rawValue = latest ? latest.metric_value?.[valueKey] : undefined;
  const hasValue = typeof rawValue === "number";

  const state: AnalyticsCardState = loading
    ? { kind: "loading", label: "Loading experimental metrics…" }
    : !hasValue
      ? { kind: "unavailable", reason: FRONTIER_UNAVAILABLE_REASON[metricName] }
      : { kind: "live" };

  return (
    <AnalyticsCard
      title={title}
      state={state}
      className="span-4"
      headerExtra={hasValue ? <ExperimentalBadge /> : undefined}
    >
      {hasValue && latest && (
        <div data-testid={`frontier-${metricName}`}>
          <strong style={{ fontSize: "1.4rem" }}>
            {Number(rawValue).toFixed(2)}
            {unit ? ` ${unit}` : ""}
          </strong>
          <p className="kicker" style={{ marginTop: 4 }}>
            {forName.length} sample{forName.length === 1 ? "" : "s"} · source {latest.source}
            {latest.sample_size != null ? ` · n=${latest.sample_size}` : ""}
          </p>
          {latest.stability_note && (
            <p className="kicker" style={{ marginTop: 4 }}>
              {latest.stability_note}
            </p>
          )}
        </div>
      )}
    </AnalyticsCard>
  );
}

