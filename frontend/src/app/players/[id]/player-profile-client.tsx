"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download } from "lucide-react";
import { FootballShell } from "@/components/football-shell";
import { HeatMap, PlayerPortrait, TrendLine } from "@/components/visuals";
import { MockBadge } from "@/components/mock-badge";
import { useAppState } from "@/lib/app-state";

export function PlayerProfileClient({ id }: { id: string }) {
  const router = useRouter();
  const { data, getPlayerById, setSelectedPlayerId } = useAppState();
  const player = getPlayerById(id);

  if (!player) {
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

  const exportProfile = () => {
    const lines = [
      `Player Profile — #${player.jersey} ${player.name}`,
      `Position: ${player.position} · Group: ${player.group}`,
      `Max Speed: ${player.maxSpeed} MPH`,
      `Distance: ${player.distance} YDS`,
      `Avg Separation: ${player.separation} YDS`,
      `Identity Confidence: ${Math.round(player.confidence * 100)}%`,
      `Trend: ${player.trend.join(", ")}`,
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
                router.push(`/players/${encodeURIComponent(e.target.value)}`);
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
            <MetricLine label="Identity Confidence" value={`${Math.round(player.confidence * 100)}%`} />
          </div>
        </section>

        <section className="panel panel-pad span-8">
          <h2 className="panel-title">Performance Metrics</h2>
          <div className="metric-grid" style={{ marginTop: 12 }}>
            <Metric label="Max Speed" value={String(player.maxSpeed)} unit="MPH" />
            <Metric label="Distance" value={String(player.distance)} unit="YDS" />
            <Metric label="Avg Separation" value={String(player.separation)} unit="YDS" />
            <Metric label="Identity" value={`${Math.round(player.confidence * 100)}%`} unit="" />
          </div>
          <div style={{ marginTop: 14 }}>
            <h3 className="panel-title" style={{ fontSize: "0.78rem" }}>Trend</h3>
            <TrendLine data={player.trend} />
          </div>
        </section>

        <section className="panel panel-pad span-6">
          <h2 className="panel-title">Biomechanics <MockBadge status="mock" /></h2>
          {/* Sample values — per-player biomechanics wire-up tracked in #100. */}
          <div className="list-stack" style={{ marginTop: 12 }}>
            <MetricLine label="Pad Level" value="-4.2°" />
            <MetricLine label="Torso Angle" value="18.6°" />
            <MetricLine label="Stride Length" value="6.2 ft" />
            <MetricLine label="Stride Symmetry" value="92%" />
            <MetricLine label="Breakpoint Angle" value="18.4°" />
          </div>
        </section>

        <section className="panel panel-pad span-6">
          <h2 className="panel-title">Field Coverage</h2>
          <HeatMap />
        </section>

        <section className="panel panel-pad span-12">
          <h2 className="panel-title">Position Group · Quick Switch</h2>
          <div className="list-stack" style={{ marginTop: 12 }}>
            {others.map((p) => (
              <Link key={p.id} href={`/players/${encodeURIComponent(p.id)}`} className="table-row table-row-link">
                <strong>#{p.jersey} {p.name}</strong>
                <span>{p.position}</span>
                <span>{p.maxSpeed} MPH</span>
                <span>{p.distance} YDS</span>
                <span className="status-pill info">{Math.round(p.confidence * 100)}%</span>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </FootballShell>
  );
}

function Metric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {unit && <small>{unit}</small>}
    </div>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span className="small-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
