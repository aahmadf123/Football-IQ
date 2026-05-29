"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FootballShell } from "@/components/football-shell";
import { AnalyticsCard, type AnalyticsCardState } from "@/components/analytics-card";
import { FieldDiagram } from "@/components/field-diagram";
import { useAppState } from "@/lib/app-state";
import {
  fetchCfbdMacBenchmark,
  fetchCfbdToledoSchedule,
  fetchCfbdToledoTeam,
} from "@/lib/api";
import type {
  CfbdCacheMeta,
  CfbdMacBenchmarkResponse,
  CfbdScheduleResponse,
  CfbdTeamResponse,
} from "@/lib/types";

const SOURCE_LABEL = "CollegeFootballData.com";

type FetchState<T> =
  | { kind: "loading" }
  | { kind: "offline" }
  | { kind: "error"; message: string }
  | { kind: "ready"; resp: T };

export default function CollegeDataPage() {
  return (
    <FootballShell activePage="college-data">
      <CollegeDataView />
    </FootballShell>
  );
}

function CollegeDataView() {
  const { authToken } = useAppState();
  const [team, setTeam] = useState<FetchState<CfbdTeamResponse>>({ kind: "loading" });
  const [schedule, setSchedule] = useState<FetchState<CfbdScheduleResponse>>({ kind: "loading" });
  const [benchmark, setBenchmark] = useState<FetchState<CfbdMacBenchmarkResponse>>({
    kind: "loading",
  });

  const apiConfigured = !!process.env.NEXT_PUBLIC_API_URL;

  const load = useCallback(async () => {
    if (!apiConfigured) {
      setTeam({ kind: "offline" });
      setSchedule({ kind: "offline" });
      setBenchmark({ kind: "offline" });
      return;
    }
    setTeam({ kind: "loading" });
    setSchedule({ kind: "loading" });
    setBenchmark({ kind: "loading" });

    const run = async <T,>(
      fn: () => Promise<T>,
      set: (s: FetchState<T>) => void,
    ): Promise<void> => {
      try {
        set({ kind: "ready", resp: await fn() });
      } catch (err) {
        set({ kind: "error", message: err instanceof Error ? err.message : String(err) });
      }
    };

    await Promise.all([
      run(() => fetchCfbdToledoTeam(authToken), setTeam),
      run(() => fetchCfbdToledoSchedule(undefined, authToken), setSchedule),
      run(() => fetchCfbdMacBenchmark(undefined, authToken), setBenchmark),
    ]);
  }, [apiConfigured, authToken]);

  useEffect(() => {
    load();
  }, [load]);

  // Aggregate cache freshness across whichever responses have loaded.
  const caches = useMemo<CfbdCacheMeta[]>(() => {
    const out: CfbdCacheMeta[] = [];
    if (team.kind === "ready") out.push(team.resp.cache);
    if (schedule.kind === "ready") out.push(schedule.resp.cache);
    if (benchmark.kind === "ready") out.push(benchmark.resp.cache);
    return out;
  }, [team, schedule, benchmark]);

  const banner = useMemo<BannerInfo | null>(() => {
    if (!apiConfigured) {
      return {
        tone: "unavailable",
        message:
          "Backend offline — set NEXT_PUBLIC_API_URL so cached CFBD analytics can load.",
      };
    }
    const anyError =
      team.kind === "error" || schedule.kind === "error" || benchmark.kind === "error";
    const syncError = caches.some((c) => c.sync_status === "error");
    if (anyError || syncError) {
      return {
        tone: "unavailable",
        message:
          "CFBD data is currently unavailable. Showing the last successfully cached data if any exists.",
      };
    }
    const lastSync = caches
      .map((c) => c.last_synced_at)
      .filter((v): v is string => !!v)
      .sort()
      .at(-1);
    // Only warn about staleness when data was actually synced before but is now
    // old. A never-synced (empty) cache is communicated by the per-card empty
    // states, not a misleading "out of date" banner.
    if (caches.some((c) => c.stale && c.last_synced_at)) {
      return {
        tone: "stale",
        message: lastSync
          ? `Cached CFBD data may be out of date (last synced ${formatDate(lastSync)}).`
          : "Cached CFBD data may be out of date.",
      };
    }
    return null;
  }, [apiConfigured, team, schedule, benchmark, caches]);

  return (
    <div className="content-grid">
      {banner && (
        <div
          className="span-12"
          data-testid="cfbd-banner"
          data-banner-tone={banner.tone}
          style={{
            padding: "10px 14px",
            borderRadius: 8,
            border: "1px solid",
            borderColor: banner.tone === "unavailable" ? "var(--accent-red, #f87171)" : "var(--gold)",
            background:
              banner.tone === "unavailable"
                ? "oklch(0.35 0.18 25 / 0.18)"
                : "oklch(0.65 0.18 80 / 0.14)",
            color: "var(--text)",
            fontSize: "0.85rem",
          }}
        >
          {banner.message}
        </div>
      )}

      <AnalyticsCard
        title="Toledo Team"
        state={toCardState(team, (r) => (r.team ? "live" : "empty"), load, {
          empty: "No cached Toledo team record yet. Run the CFBD ingestion (Issues #161/#162).",
        })}
        className="span-4"
      >
        {team.kind === "ready" && team.resp.team && (
          <div className="list-stack" style={{ gap: 4 }}>
            <Row label="School" value={team.resp.team.school} />
            <Row label="Mascot" value={team.resp.team.mascot ?? "—"} />
            <Row label="Conference" value={team.resp.team.conference ?? "—"} />
            <Row label="Division" value={team.resp.team.division ?? "—"} />
          </div>
        )}
      </AnalyticsCard>

      <AnalyticsCard
        title="Toledo Schedule"
        state={toCardState(
          schedule,
          (r) => (r.games.length > 0 ? "live" : "empty"),
          load,
          { empty: "No cached games for Toledo yet." },
        )}
        className="span-8"
      >
        {schedule.kind === "ready" && (
          <div className="list-stack" style={{ gap: 4 }} data-testid="cfbd-schedule">
            {schedule.resp.games.map((g) => (
              <div
                key={g.cfbd_game_id}
                className="status-row"
                style={{ gridTemplateColumns: "70px 1fr auto" }}
              >
                <span className="kicker">{g.start_date ? formatDate(g.start_date) : "TBD"}</span>
                <strong>
                  {g.away_team} @ {g.home_team}
                </strong>
                <span>
                  {g.home_points != null && g.away_points != null
                    ? `${g.away_points}–${g.home_points}`
                    : "—"}
                </span>
              </div>
            ))}
          </div>
        )}
      </AnalyticsCard>

      <AnalyticsCard
        title="MAC Benchmark (Points)"
        state={toCardState(
          benchmark,
          (r) => (r.teams.length > 0 ? "live" : "empty"),
          load,
          { empty: "No cached MAC team game stats yet." },
        )}
        className="span-8"
      >
        {benchmark.kind === "ready" && (
          <div className="list-stack" style={{ gap: 4 }} data-testid="cfbd-benchmark">
            {benchmark.resp.teams.map((t) => (
              <div
                key={t.team}
                className="status-row"
                style={{ gridTemplateColumns: "1fr 48px 64px 64px" }}
              >
                <strong>{t.team}</strong>
                <span title="Games">{t.games}</span>
                <span title="Avg points for">{fmtNum(t.avg_points_for)}</span>
                <span title="Point differential">{fmtSigned(t.point_differential)}</span>
              </div>
            ))}
          </div>
        )}
      </AnalyticsCard>

      <AnalyticsCard
        title="Field Schematic (visualization spike #169)"
        state={{
          kind: "gated",
          reason:
            "Generic NCAA field rendered natively in SVG — no R / sportypy runtime dependency. Calibrated route overlays land with the tracking pipeline (#127/#128/#129).",
        }}
        className="span-4"
      />
      <section className="panel panel-pad span-4" data-testid="cfbd-field-sample">
        <FieldDiagram />
      </section>

      <div
        className="span-12 kicker"
        data-testid="cfbd-source-label"
        style={{ textAlign: "right" }}
      >
        Source: {SOURCE_LABEL}. CFBD data is external context and is not derived from Toledo film.
      </div>
    </div>
  );
}

interface BannerInfo {
  tone: "stale" | "unavailable";
  message: string;
}

function toCardState<T>(
  state: FetchState<T>,
  liveOrEmpty: (resp: T) => "live" | "empty",
  retry: () => void,
  copy: { empty: string },
): AnalyticsCardState {
  switch (state.kind) {
    case "loading":
      return { kind: "loading", label: "Loading cached CFBD data…" };
    case "offline":
      return {
        kind: "unavailable",
        reason: "Backend offline — set NEXT_PUBLIC_API_URL to load cached CFBD analytics.",
      };
    case "error":
      return { kind: "error", message: state.message, onRetry: retry };
    case "ready":
      return liveOrEmpty(state.resp) === "live"
        ? { kind: "live" }
        : { kind: "empty", reason: copy.empty };
  }
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-row" style={{ gridTemplateColumns: "100px 1fr" }}>
      <span className="kicker">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatDate(value: string): string {
  try {
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return value;
  }
}

function fmtNum(value: number | null): string {
  return value == null ? "—" : value.toFixed(1);
}

function fmtSigned(value: number | null): string {
  if (value == null) return "—";
  return value > 0 ? `+${value.toFixed(1)}` : value.toFixed(1);
}
