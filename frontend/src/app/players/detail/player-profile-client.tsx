"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Download } from "lucide-react";
import { FootballShell } from "@/components/football-shell";
import { Metric, MetricLine } from "@/components/shared/metric";
import { PlayerPortrait } from "@/components/shared/player-portrait";
import { TrendLine } from "@/components/shared/trend-line";
import { fmtMetric, playerProfileHref } from "@/components/players-view";
import { apiPlayerToSummary, useAppState } from "@/lib/app-state";
import { fetchPlayer } from "@/lib/api";
import type { PlayerSummary } from "@/lib/types";

type LoadState = "idle" | "loading" | "ready" | "missing" | "error";

export function PlayerProfileClient({ id }: { id: string }) {
  const router = useRouter();
  const { data, getPlayerById, setSelectedPlayerId, mockMode, authToken } = useAppState();
  const cached = getPlayerById(id);

  const [player, setPlayer] = useState<PlayerSummary | undefined>(cached);
  const [loadState, setLoadState] = useState<LoadState>(cached ? "ready" : "idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Pull live identity from /api/v1/players/{id} when not in mock mode. The
  // cached entry from the roster fetch is shown immediately as a fast path;
  // the backend response overrides it on success.
  useEffect(() => {
    if (mockMode) {
      setPlayer(cached);
      setLoadState(cached ? "ready" : "missing");
      return;
    }
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      if (cached) {
        setPlayer(cached);
        setLoadState("ready");
      } else {
        setErrorMessage("API is not configured (NEXT_PUBLIC_API_URL is unset).");
        setLoadState("error");
      }
      return;
    }
    let cancelled = false;
    if (cached) setPlayer(cached);
    setLoadState(cached ? "ready" : "loading");
    (async () => {
      try {
        const apiPlayer = await fetchPlayer(id, authToken);
        if (cancelled) return;
        setPlayer(apiPlayerToSummary(apiPlayer));
        setLoadState("ready");
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        if (/404/.test(message)) {
          setLoadState("missing");
        } else {
          setErrorMessage(message);
          setLoadState(cached ? "ready" : "error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, mockMode, authToken, cached]);

  if (loadState === "loading") {
    return (
      <FootballShell activePage="players">
        <div className="content-grid">
          <section className="panel panel-pad span-12">
            <h2 className="panel-title">Loading player…</h2>
            <p className="kicker" style={{ marginTop: 8 }}>
              Fetching player <strong>{id}</strong> from the backend.
            </p>
          </section>
        </div>
      </FootballShell>
    );
  }

  if (loadState === "error") {
    return (
      <FootballShell activePage="players">
        <div className="content-grid">
          <section className="panel panel-pad span-12">
            <h2 className="panel-title">Could not load player</h2>
            <p className="kicker" style={{ marginTop: 8 }}>
              {errorMessage ?? "An unexpected error occurred."}
            </p>
            <Link href="/players" className="control-button primary" style={{ marginTop: 12, textDecoration: "none", display: "inline-flex" }}>
              <ArrowLeft size={15} /> Back to Roster
            </Link>
          </section>
        </div>
      </FootballShell>
    );
  }

  if (!player || loadState === "missing") {
    return (
      <FootballShell activePage="players">
        <div className="content-grid">
          <section className="panel panel-pad span-12">
            <h2 className="panel-title">Player not found</h2>
            <p className="kicker" style={{ marginTop: 8 }}>
              We couldn&apos;t find a player with id <strong>{id}</strong>.
            </p>
            <Link href="/players" className="control-button primary" style={{ marginTop: 12, textDecoration: "none", display: "inline-flex" }}>
              <ArrowLeft size={15} /> Back to Roster
            </Link>
          </section>
        </div>
      </FootballShell>
    );
  }

  const others = data.players.filter((p) => p.id !== player.id);
  const metricsAvailable = player.maxSpeed != null || player.distance != null || player.separation != null;
  const trendAvailable = player.trend && player.trend.length > 0;
  const confidenceLabel = player.confidence != null ? `${Math.round(player.confidence * 100)}%` : "—";

  const exportProfile = () => {
    const lines = [
      `Player Profile — #${player.jersey} ${player.name}`,
      `Position: ${player.position} · Group: ${player.group}`,
      `Max Speed: ${player.maxSpeed != null ? `${player.maxSpeed} MPH` : "not available"}`,
      `Distance: ${player.distance != null ? `${player.distance} YDS` : "not available"}`,
      `Avg Separation: ${player.separation != null ? `${player.separation} YDS` : "not available"}`,
      `Identity Confidence: ${confidenceLabel}`,
      `Trend: ${trendAvailable ? player.trend!.join(", ") : "not available"}`,
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `player-${player.jersey}-${player.name.replace(/\s+/g, "-")}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <FootballShell activePage="players">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, gap: 12, flexWrap: "wrap" }}>
        <button type="button" className="control-button" onClick={() => router.back()}>
          <ArrowLeft size={15} /> Back
        </button>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label className="inline-select-wrap">
            <span className="kicker">Switch player</span>
            <select
              className="inline-select"
              value={player.id}
              onChange={(e) => {
                setSelectedPlayerId(e.target.value);
                router.push(playerProfileHref(e.target.value));
              }}
            >
              {data.players.map((p) => (
                <option key={p.id} value={p.id}>#{p.jersey} {p.name} · {p.position}</option>
              ))}
            </select>
          </label>
          <button className="control-button primary" onClick={exportProfile}>
            <Download size={15} /> Export Profile
          </button>
        </div>
      </div>

      <div className="content-grid">
        <section className="panel panel-pad span-4">
          <h2 className="panel-title">Identity</h2>
          <PlayerPortrait player={player} />
          <div className="list-stack" style={{ marginTop: 12 }}>
            <MetricLine label="Jersey" value={`#${player.jersey}`} />
            <MetricLine label="Name" value={player.name} />
            <MetricLine label="Position" value={player.position} />
            <MetricLine label="Group" value={player.group} />
            <MetricLine label="Identity Confidence" value={confidenceLabel} />
          </div>
        </section>

        <section className="panel panel-pad span-8">
          <h2 className="panel-title">Performance Metrics</h2>
          {metricsAvailable ? (
            <div className="metric-grid" style={{ marginTop: 12 }}>
              <Metric label="Max Speed" value={fmtMetric(player.maxSpeed)} unit="MPH" />
              <Metric label="Distance" value={fmtMetric(player.distance)} unit="YDS" />
              <Metric label="Avg Separation" value={fmtMetric(player.separation)} unit="YDS" />
              <Metric label="Identity" value={confidenceLabel} unit="" />
            </div>
          ) : (
            <p className="kicker" style={{ marginTop: 10 }}>
              Performance metrics are not wired to the live pipeline yet. They will surface once per-player tracking metrics land (#100).
            </p>
          )}
          <div style={{ marginTop: 14 }}>
            <h3 className="panel-title" style={{ fontSize: "0.78rem" }}>Trend</h3>
            <TrendLine data={player.trend} />
          </div>
        </section>

        <section className="panel panel-pad span-12">
          <h2 className="panel-title">Position Group · Quick Switch</h2>
          {others.length === 0 ? (
            <p className="kicker" style={{ marginTop: 8 }}>No other players on the roster yet.</p>
          ) : (
            <div className="list-stack" style={{ marginTop: 12 }}>
              {others.map((p) => (
                <Link key={p.id} href={playerProfileHref(p.id)} className="table-row table-row-link">
                  <strong>#{p.jersey} {p.name}</strong>
                  <span>{p.position}</span>
                  <span>{fmtMetric(p.maxSpeed)} MPH</span>
                  <span>{fmtMetric(p.distance)} YDS</span>
                  <span className="status-pill info">{p.confidence != null ? `${Math.round(p.confidence * 100)}%` : "—"}</span>
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </FootballShell>
  );
}
