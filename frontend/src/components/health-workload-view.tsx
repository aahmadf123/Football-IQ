"use client";

/**
 * Athlete health/workload surface (Issue #113), extracted from the old
 * page-renderer monolith. Role-gated: only sports-performance staff (plus
 * analytics leads / admins) see the surface; a deep link from any other role
 * falls through to a restricted notice. All values come from the backend
 * (dashboard + injury-risk rollups) or are clearly-labeled integration
 * contracts; the old illustrative "Team Load Trend" mock chart was removed
 * (#96).
 */

import { useEffect, useState } from "react";
import { useAppState } from "@/lib/app-state";
import { fetchHealthDashboard, fetchInjuryRisk } from "@/lib/api";
import { ExperimentalBadge } from "@/components/experimental-badge";
import { TrendLine } from "@/components/shared/trend-line";
import { canAccessHealthWorkload, canSeePlayerLevelRisk } from "@/lib/roles";
import {
  HEALTH_POLICY_STATEMENT,
  HEALTH_WORKLOAD_DISCLAIMER,
  HEALTH_WORKLOAD_INTEGRATIONS,
  WORKLOAD_RISK_CAVEAT,
  type HealthDashboardResponse,
  type HealthWorkloadIntegration,
  type InjuryRiskResponse,
} from "@/lib/health-workload";

export function HealthWorkloadView() {
  const { currentRole } = useAppState();

  if (!canAccessHealthWorkload(currentRole)) {
    return (
      <div className="content-grid">
        <section className="panel panel-pad span-12" data-testid="health-workload-restricted">
          <h2 className="panel-title">Health &amp; Workload — Restricted</h2>
          <p className="kicker" style={{ marginTop: 8 }}>
            This surface is limited to sports-performance staff (plus analytics
            leads and admins). Your role does not have access. Contact an
            administrator if you believe this is in error.
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="content-grid" data-testid="health-workload-surface">
      <section className="panel panel-pad span-12" data-testid="health-workload-disclaimer">
        <h2 className="panel-title">Sports-Performance Context</h2>
        <p className="kicker" style={{ marginTop: 8 }}>{HEALTH_WORKLOAD_DISCLAIMER}</p>
        <p className="kicker" style={{ marginTop: 6 }} data-testid="health-policy-statement">
          {HEALTH_POLICY_STATEMENT}
        </p>
      </section>

      <DailyAthleteStatePanel />

      <WorkloadRiskPanel />

      <section className="panel panel-pad span-12">
        <h2 className="panel-title">Data Sources</h2>
        <p className="kicker" style={{ marginTop: 6 }}>
          No source is connected yet — these are documented integration
          contracts only. No athlete data is surfaced.
        </p>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {HEALTH_WORKLOAD_INTEGRATIONS.map((integration) => (
            <IntegrationRow key={integration.source} integration={integration} />
          ))}
        </div>
      </section>

      <section className="panel panel-pad span-12">
        <h2 className="panel-title">About This Surface</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          <Insight
            title="Access"
            detail="Sports-performance staff, analytics leads, and admins only. Every read is audit-logged."
            severity="info"
          />
          <Insight
            title="Purpose"
            detail="Training-load and wellness context to support staff planning and conversations."
            severity="good"
          />
          <Insight
            title="Not for"
            detail="Medical diagnosis, injury prediction, or return-to-play decisions. This is not a medical device."
            severity="warning"
          />
        </div>
      </section>
    </div>
  );
}

// Unified daily athlete-state dashboard (Issue #9). Fuses the nightly CV
// workload rollup with the UT sources (wellness, GPS, S&C, academic calendar,
// rehab-tier injury history). The backend shapes the payload per role — this
// component only renders what it receives: player-level state + fatigue flags
// for sports-performance staff/admins, position-group aggregates for
// analysts. Every value carries its source and confidence caveat.
function DailyAthleteStatePanel() {
  const { authToken } = useAppState();
  const [dashboard, setDashboard] = useState<HealthDashboardResponse | null>(null);
  const [dashState, setDashState] = useState<"idle" | "loading" | "ready" | "error">("idle");

  useEffect(() => {
    if (!authToken) {
      setDashboard(null);
      setDashState("idle");
      return;
    }
    let cancelled = false;
    setDashState("loading");
    fetchHealthDashboard({ days: 14 }, authToken)
      .then((payload) => {
        if (cancelled) return;
        setDashboard(payload);
        setDashState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setDashboard(null);
        setDashState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [authToken]);

  const players = dashboard?.players ?? [];
  const aggregates = dashboard?.aggregates ?? [];
  const fatigueFlags = dashboard?.fatigue_flags ?? [];
  const trends = dashboard?.trends ?? {};
  const academic = dashboard?.academic_context ?? [];
  const connectedSources =
    dashboard?.integrations?.filter((i) => i.status === "connected") ?? [];

  return (
    <section className="panel panel-pad span-12" data-testid="health-daily-state">
      <h2 className="panel-title">
        Daily Athlete State <ExperimentalBadge label="Staff context" />
      </h2>
      <p className="kicker" style={{ marginTop: 6 }}>
        Fused view: CV workload rollup joined with wellness, GPS/wearables, S&amp;C,
        academic calendar, and availability context. Values are shown with their
        source and confidence — nothing here is ground truth.
      </p>

      {dashState === "idle" && (
        <p className="kicker" style={{ marginTop: 12 }}>
          Sign in to load the fused daily athlete state.
        </p>
      )}
      {dashState === "loading" && (
        <p className="kicker" style={{ marginTop: 12 }}>Loading daily athlete state…</p>
      )}
      {dashState === "error" && (
        <p className="kicker" style={{ marginTop: 12 }}>
          Could not load the dashboard. Nothing is shown rather than stale values.
        </p>
      )}

      {dashState === "ready" && dashboard && (
        <>
          <p className="kicker" style={{ marginTop: 8 }}>
            {dashboard.date} · sources connected:{" "}
            {connectedSources.length > 0
              ? connectedSources.map((s) => s.display_name).join(", ")
              : "none yet (CV rollup only)"}
            {academic.length > 0 &&
              ` · academic context: ${academic
                .map((e) => String(e.label ?? e.event_type))
                .join(", ")}`}
          </p>

          {fatigueFlags.length > 0 && (
            <div className="list-stack" style={{ marginTop: 12 }} data-testid="fatigue-flags">
              {fatigueFlags.map((flag) => (
                <Insight
                  key={flag.alert_id}
                  title={`Fatigue flag — ${flag.position_group} (${flag.severity})`}
                  detail={`Unacknowledged workload-risk alert from the nightly rollup. ${flag.caveat}`}
                  severity="warning"
                />
              ))}
            </div>
          )}

          {dashboard.player_level && players.length > 0 && (
            <div style={{ marginTop: 12, overflowX: "auto" }}>
              <table className="data-table" data-testid="daily-state-table">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Group</th>
                    <th>CV load (yd)</th>
                    <th>ACWR</th>
                    <th>Wellness</th>
                    <th>GPS load</th>
                    <th>S&amp;C RPE</th>
                    <th>Availability</th>
                  </tr>
                </thead>
                <tbody>
                  {players.map((state) => (
                    <tr key={state.player_id}>
                      <td>
                        {state.name}
                        {state.jersey_number != null ? ` #${state.jersey_number}` : ""}
                      </td>
                      <td>{state.position_group ?? "—"}</td>
                      <td>{state.cv_workload?.daily_load ?? "—"}</td>
                      <td>{state.cv_workload?.acwr ?? "—"}</td>
                      <td>
                        {state.wellness
                          ? `soreness ${state.wellness.soreness ?? "–"} · sleep ${state.wellness.sleep_hours ?? "–"}h`
                          : "—"}
                      </td>
                      <td>{(state.gps?.player_load as number | undefined) ?? "—"}</td>
                      <td>
                        {(state.strength_conditioning?.session_rpe as number | undefined) ?? "—"}
                      </td>
                      <td>
                        {state.injury_history == null
                          ? "restricted"
                          : state.injury_history.length === 0
                            ? "available"
                            : `${state.injury_history.length} active`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {dashboard.player_level && players.length === 0 && (
            <p className="kicker" style={{ marginTop: 12 }}>
              No fused rows for this day yet — rows appear after the nightly
              workload rollup has run.
            </p>
          )}

          {!dashboard.player_level && (
            <div className="list-stack" style={{ marginTop: 12 }} data-testid="daily-state-aggregates">
              {aggregates.length === 0 ? (
                <Insight
                  title="Position-group view"
                  detail="No aggregate rows for this day yet. Player-level state is limited to sports-performance staff."
                  severity="info"
                />
              ) : (
                aggregates.map((agg) => (
                  <Insight
                    key={agg.position_group}
                    title={`${agg.position_group} — ${agg.player_count} player${agg.player_count === 1 ? "" : "s"}`}
                    detail={`Mean ACWR ${agg.mean_acwr ?? "–"} · mean load ${agg.mean_daily_load ?? "–"} yd. ${agg.caveat}`}
                    severity="info"
                  />
                ))
              )}
            </div>
          )}

          {Object.keys(trends).length > 0 && (
            <div style={{ marginTop: 16 }} data-testid="workload-trends">
              <h3 className="panel-title" style={{ fontSize: 14 }}>
                Workload trends by position group (mean ACWR, {dashboard.days}d)
              </h3>
              <div className="list-stack" style={{ marginTop: 8 }}>
                {Object.entries(trends).map(([group, points]) => {
                  const series = points
                    .map((p) => p.mean_acwr)
                    .filter((v): v is number => v != null);
                  return (
                    <div
                      key={group}
                      className="insight-row"
                      style={{ gridTemplateColumns: "80px 1fr" }}
                    >
                      <strong>{group}</strong>
                      {series.length >= 2 ? <TrendLine data={series} /> : <span>—</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

// Workload-risk signals panel (Issue #149). Player-level rows (ACWR, gait
// asymmetry, heuristic risk score, sprint count) render only for
// sports-performance staff + admins; analysts see position-group aggregates.
// The backend enforces the same split — this gate is presentation only.
// Every value ships with the non-diagnostic caveat.
function WorkloadRiskPanel() {
  const { currentRole, authToken } = useAppState();
  const [risk, setRisk] = useState<InjuryRiskResponse | null>(null);
  const [riskState, setRiskState] = useState<"idle" | "loading" | "ready" | "error">("idle");

  useEffect(() => {
    if (!authToken) {
      setRisk(null);
      setRiskState("idle");
      return;
    }
    let cancelled = false;
    setRiskState("loading");
    fetchInjuryRisk({ days: 14 }, authToken)
      .then((payload) => {
        if (cancelled) return;
        setRisk(payload);
        setRiskState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setRisk(null);
        setRiskState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [authToken]);

  const playerLevel = canSeePlayerLevelRisk(currentRole);
  const rows = risk?.rows ?? [];
  const aggregates = risk?.aggregates ?? [];
  const flagged = rows.filter((row) => {
    const latest = row.latest;
    if (!latest) return false;
    return (latest.acwr ?? 0) > 1.5 || (latest.asymmetry_index ?? 0) > 1.3;
  });

  return (
    <section className="panel panel-pad span-12" data-testid="health-workload-risk">
      <h2 className="panel-title">
        Workload Risk Signals <ExperimentalBadge />
      </h2>
      <p className="kicker" style={{ marginTop: 6 }} data-testid="workload-risk-caveat">
        {WORKLOAD_RISK_CAVEAT} Values come from the nightly CV workload rollup
        (acute:chronic ratio over 7/28 days, pose-based gait asymmetry).
      </p>

      {riskState === "idle" && (
        <p className="kicker" style={{ marginTop: 12 }}>
          Sign in to load the nightly workload rollup.
        </p>
      )}
      {riskState === "loading" && (
        <p className="kicker" style={{ marginTop: 12 }}>Loading nightly rollup…</p>
      )}
      {riskState === "error" && (
        <p className="kicker" style={{ marginTop: 12 }}>
          Could not load workload risk data. The surface stays empty rather than
          showing stale or illustrative risk values.
        </p>
      )}

      {riskState === "ready" && playerLevel && (
        <>
          {flagged.length > 0 && (
            <div className="list-stack" style={{ marginTop: 12 }} data-testid="workload-risk-flags">
              {flagged.map((row) => {
                const latest = row.latest;
                const reasons = latest?.risk_reason_codes?.join(", ") ?? "";
                return (
                  <Insight
                    key={row.player_id}
                    title={`${row.name} — review flagged`}
                    detail={`ACWR ${latest?.acwr ?? "–"} · asymmetry ${latest?.asymmetry_index ?? "–"} · ${reasons}. ${WORKLOAD_RISK_CAVEAT}`}
                    severity="warning"
                  />
                );
              })}
            </div>
          )}
          {rows.length === 0 ? (
            <p className="kicker" style={{ marginTop: 12 }}>
              No rollup rows yet — rows appear after the nightly workload job has
              processed identity-confident film.
            </p>
          ) : (
            <div style={{ marginTop: 12, overflowX: "auto" }}>
              <table className="data-table" data-testid="workload-risk-table">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Group</th>
                    <th>ACWR (7d/28d)</th>
                    <th>Asymmetry</th>
                    <th>Risk score</th>
                    <th>Sprints</th>
                    <th>Confidence</th>
                    <th>14-day ACWR</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const latest = row.latest;
                    const acwrSeries = row.series
                      .map((point) => point.acwr)
                      .filter((value): value is number => value != null);
                    return (
                      <tr key={row.player_id}>
                        <td>
                          {row.name}
                          {row.jersey_number != null ? ` #${row.jersey_number}` : ""}
                        </td>
                        <td>{row.position_group ?? "—"}</td>
                        <td>{latest?.acwr ?? "—"}</td>
                        <td>{latest?.asymmetry_index ?? "—"}</td>
                        <td>{latest?.injury_risk_score ?? "—"}</td>
                        <td>{latest?.sprint_count ?? "—"}</td>
                        <td>{latest?.confidence != null ? latest.confidence.toFixed(2) : "—"}</td>
                        <td style={{ minWidth: 120 }}>
                          {acwrSeries.length >= 2 ? <TrendLine data={acwrSeries} /> : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {riskState === "ready" && !playerLevel && (
        <div className="list-stack" style={{ marginTop: 12 }} data-testid="workload-risk-aggregates">
          <Insight
            title="Position-group view"
            detail="Your role sees aggregate workload context only. Player-level risk is limited to sports-performance staff."
            severity="info"
          />
          {aggregates.map((agg) => (
            <Insight
              key={agg.position_group}
              title={`${agg.position_group} — ${agg.player_count} player${agg.player_count === 1 ? "" : "s"}`}
              detail={`Mean ACWR ${agg.mean_acwr ?? "–"} · mean asymmetry ${agg.mean_asymmetry_index ?? "–"} · max risk ${agg.max_injury_risk_score ?? "–"}. ${WORKLOAD_RISK_CAVEAT}`}
              severity="info"
            />
          ))}
        </div>
      )}
    </section>
  );
}

function IntegrationRow({ integration }: { integration: HealthWorkloadIntegration }) {
  const connected = integration.status === "connected";
  return (
    <div
      className="insight-row"
      style={{ gridTemplateColumns: "1fr auto" }}
      data-testid={`hw-integration-${integration.source}`}
    >
      <span>
        <strong>{integration.displayName}</strong>
        <br />
        <small style={{ color: "var(--muted)" }}>
          {integration.description}
          {" · "}
          {integration.dataCategories.join(", ")}
        </small>
      </span>
      <span
        className={`status-pill ${connected ? "" : "warning"}`}
        style={{ alignSelf: "center", whiteSpace: "nowrap" }}
      >
        {connected ? "Connected" : "Not connected"}
      </span>
    </div>
  );
}

function Insight({ title, detail, severity }: { title: string; detail: string; severity: "good" | "warning" | "danger" | "info" }) {
  const className = severity === "danger" ? "danger" : severity === "warning" ? "warning" : severity === "info" ? "info" : "";
  return (
    <div className="insight-row" style={{ gridTemplateColumns: "auto 1fr" }}>
      <span className={`status-pill ${className}`} style={{ width: 24, height: 24, padding: 0, justifyContent: "center" }}>•</span>
      <span><strong>{title}</strong><br /><small style={{ color: "var(--muted)" }}>{detail}</small></span>
    </div>
  );
}
