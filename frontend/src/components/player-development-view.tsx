"use client";

/**
 * Player Development (extracted from the old page-renderer monolith).
 *
 * Real surfaces only: the selected player's identity focus, the
 * body-orientation proxy + effort review candidates from /api/v1/metrics, and
 * the coach corrections flow (POST /api/v1/corrections). The old hardcoded
 * "Best Teaching Clips" mock grid was removed (#96).
 */

import Link from "next/link";
import { CheckCircle2, Pause, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useAppState } from "@/lib/app-state";
import { createCorrection, fetchMetrics, type ApiMetric } from "@/lib/api";
import { MetricLine } from "@/components/shared/metric";
import { PlayerPortrait } from "@/components/shared/player-portrait";
import { TrendLine } from "@/components/shared/trend-line";
import { PlayerFocus, playerProfileHref } from "@/components/players-view";

export function PlayerDevelopmentView() {
  const { data, selectedPlayer, setSelectedPlayerId, filteredPlayers, authToken } = useAppState();
  const pool = filteredPlayers.length ? filteredPlayers : data.players;
  const [developmentMetrics, setDevelopmentMetrics] = useState<ApiMetric[]>([]);
  const [metricsState, setMetricsState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [correctionState, setCorrectionState] = useState<Record<string, "saving" | "saved" | "error">>({});
  const selectedPlayerId = selectedPlayer?.id;

  useEffect(() => {
    if (!authToken || !selectedPlayerId) {
      setDevelopmentMetrics([]);
      setMetricsState("idle");
      setMetricsError(null);
      return;
    }
    let cancelled = false;
    setMetricsState("loading");
    setMetricsError(null);
    Promise.all([
      fetchMetrics({ metric_name: "effort_review_candidate", player_id: selectedPlayerId, limit: 200 }, authToken),
      fetchMetrics({ metric_name: "pose_body_orientation_proxy", player_id: selectedPlayerId, limit: 200 }, authToken),
    ])
      .then(([effort, orientation]) => {
        if (cancelled) return;
        setDevelopmentMetrics([...effort, ...orientation]);
        setMetricsState("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDevelopmentMetrics([]);
        setMetricsError(err instanceof Error ? err.message : String(err));
        setMetricsState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [authToken, selectedPlayerId]);

  if (!selectedPlayer) {
    return (
      <div className="content-grid">
        <section className="panel panel-pad span-12">
          <h2 className="panel-title">Player Development</h2>
          <p className="kicker" style={{ marginTop: 8 }}>No players yet.</p>
        </section>
      </div>
    );
  }

  const playerMetrics = developmentMetrics.filter(
    (metric) => metric.metric_value.player_id === selectedPlayer.id,
  );
  const effortMetrics = playerMetrics.filter((metric) => metric.metric_name === "effort_review_candidate");
  const orientationMetrics = playerMetrics.filter(
    (metric) => metric.metric_name === "pose_body_orientation_proxy",
  );

  const submitEffortCorrection = async (metric: ApiMetric, loafFlag: boolean) => {
    if (!authToken) return;
    setCorrectionState((cur) => ({ ...cur, [metric.id]: "saving" }));
    try {
      await createCorrection(
        {
          clip_id: metric.clip_id,
          correction_type: "effort_tag",
          original_value: { metric_id: metric.id, ...metric.metric_value },
          corrected_value: {
            metric_id: metric.id,
            player_id: selectedPlayer.id,
            loaf_flag: loafFlag,
            review_state: loafFlag ? "coach_confirmed" : "coach_cleared",
          },
          training_eligible: true,
        },
        authToken,
      );
      setCorrectionState((cur) => ({ ...cur, [metric.id]: "saved" }));
    } catch {
      setCorrectionState((cur) => ({ ...cur, [metric.id]: "error" }));
    }
  };

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <PlayerFocus player={selectedPlayer} allPlayers={pool} onSelect={setSelectedPlayerId} />
        <Link href={playerProfileHref(selectedPlayer.id)} className="control-button primary" style={{ marginTop: 12, textDecoration: "none", justifyContent: "center" }}>
          <UserRound size={15} /> Open Full Profile
        </Link>
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Body-Orientation Proxy</h2>
        <PlayerPortrait player={selectedPlayer} />
        <DevelopmentMetricState
          authToken={authToken}
          state={metricsState}
          error={metricsError}
          empty={orientationMetrics.length === 0}
          emptyMessage="No body-orientation review candidates for this player."
        />
        {orientationMetrics.slice(0, 3).map((metric) => (
          <BodyOrientationRow key={metric.id} metric={metric} />
        ))}
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Trend Lines</h2>
        <TrendLine data={selectedPlayer.trend} />
      </section>
      <section className="panel panel-pad span-12">
        <h2 className="panel-title">Effort Review Candidates</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          <DevelopmentMetricState
            authToken={authToken}
            state={metricsState}
            error={metricsError}
            empty={effortMetrics.length === 0}
            emptyMessage="No effort review candidates for this player."
          />
          {effortMetrics.slice(0, 6).map((metric) => (
            <EffortReviewRow
              key={metric.id}
              metric={metric}
              status={correctionState[metric.id]}
              onConfirm={() => submitEffortCorrection(metric, true)}
              onClear={() => submitEffortCorrection(metric, false)}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

function DevelopmentMetricState({
  authToken,
  state,
  error,
  empty,
  emptyMessage,
}: {
  authToken?: string;
  state: "idle" | "loading" | "ready" | "error";
  error: string | null;
  empty: boolean;
  emptyMessage: string;
}) {
  if (!authToken) {
    return <p className="kicker" style={{ marginTop: 8 }}>Sign in to view live review candidates.</p>;
  }
  if (state === "loading") {
    return <p className="kicker" style={{ marginTop: 8 }}>Loading review candidates…</p>;
  }
  if (state === "error") {
    return <p className="kicker" style={{ marginTop: 8 }}>{error ?? "Review candidates unavailable."}</p>;
  }
  if (state === "ready" && empty) {
    return <p className="kicker" style={{ marginTop: 8 }}>{emptyMessage}</p>;
  }
  return null;
}

function EffortReviewRow({
  metric,
  status,
  onConfirm,
  onClear,
}: {
  metric: ApiMetric;
  status?: "saving" | "saved" | "error";
  onConfirm: () => void;
  onClear: () => void;
}) {
  const value = metric.metric_value;
  const flagged = metric.loaf_flag === true || value.loaf_flag === true;
  const reasonCodes = Array.isArray(value.reason_codes) ? value.reason_codes.join(", ") : "review";
  return (
    <div className="insight-row" style={{ gridTemplateColumns: "1fr auto" }}>
      <span>
        <strong>{flagged ? "Possible effort drop" : "Effort range check"}</strong>
        <br />
        <small style={{ color: "var(--muted)" }}>
          z {formatMaybeNumber(metric.effort_zscore)} · confidence {formatMaybePct(metric.confidence)}
          {" · "}{reasonCodes}
        </small>
      </span>
      <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <button className="icon-button" aria-label="Confirm effort review candidate" onClick={onConfirm}>
          <CheckCircle2 size={15} />
        </button>
        <button className="icon-button" aria-label="Clear effort review candidate" onClick={onClear}>
          <Pause size={15} />
        </button>
        {status === "saving" && <small className="kicker">Saving</small>}
        {status === "saved" && <small className="kicker">Saved</small>}
        {status === "error" && <small className="kicker">Error</small>}
      </span>
    </div>
  );
}

function BodyOrientationRow({ metric }: { metric: ApiMetric }) {
  const value = metric.metric_value;
  return (
    <div className="list-stack" style={{ marginTop: 8, gap: 2 }}>
      <MetricLine label="Proxy class" value={orientationLabel(value.orientation_class)} />
      <MetricLine label="Head yaw" value={`${formatMaybeNumber(value.head_yaw_deg)}°`} />
      <MetricLine label="Confidence" value={formatMaybePct(metric.confidence)} />
      <MetricLine label="Review state" value={String(value.review_state ?? "needs review")} />
    </div>
  );
}

function formatMaybeNumber(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? String(Math.round(value * 10) / 10) : "—";
}

function formatMaybePct(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "—";
}

function orientationLabel(value: unknown): string {
  switch (value) {
    case "body_inside":
      return "Inside";
    case "body_on_receiver":
      return "Receiver";
    case "body_backfield":
      return "Backfield";
    default:
      return "Needs review";
  }
}
