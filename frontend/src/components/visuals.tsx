import Image from "next/image";
import type { PlayerSummary } from "@/lib/types";

const fieldPlayers = [
  ["11", "18%", "42%", "var(--blue)"],
  ["17", "27%", "33%", "var(--blue)"],
  ["28", "24%", "63%", "var(--gold)"],
  ["9", "47%", "44%", "var(--blue)"],
  ["54", "56%", "48%", "var(--blue)"],
  ["22", "66%", "62%", "var(--green)"],
  ["31", "77%", "54%", "var(--green)"],
  ["4", "82%", "33%", "var(--orange)"],
  ["8", "87%", "45%", "var(--orange)"],
] as const;

const routes = [
  ["19%", "45%", "130px", "-28deg", "var(--gold)"],
  ["50%", "46%", "122px", "-22deg", "var(--gold)"],
  ["66%", "58%", "92px", "26deg", "var(--green)"],
  ["78%", "50%", "96px", "-38deg", "var(--orange)"],
] as const;

export function FieldStage() {
  return (
    <div className="field-stage">
      <Image src="/brand/toledo-rocket.png" width={180} height={105} alt="" className="midfield-logo" />
      <span className="yard-number" style={{ left: "15%", top: "14%" }}>40</span>
      <span className="yard-number" style={{ left: "46%", top: "14%" }}>50</span>
      <span className="yard-number" style={{ right: "16%", top: "14%" }}>40</span>
      <span className="yard-number" style={{ left: "18%", bottom: "13%" }}>40</span>
      <span className="yard-number" style={{ right: "18%", bottom: "13%" }}>40</span>
      {routes.map(([x, y, w, r, color], index) => (
        <i
          key={index}
          className="route-line"
          style={{ "--x": x, "--y": y, "--w": w, "--r": r, "--route": color } as React.CSSProperties}
        />
      ))}
      {fieldPlayers.map(([number, x, y, color]) => (
        <span key={number} className="player-dot" style={{ "--x": x, "--y": y, "--dot": color } as React.CSSProperties}>
          {number}
        </span>
      ))}
    </div>
  );
}

export function VideoControls() {
  return (
    <>
      <div className="video-controls">
        <span style={{ fontWeight: 900 }}>▶</span>
        <strong>00:07 / 00:12</strong>
        <div className="progress"><i style={{ "--value": "58%" } as React.CSSProperties} /></div>
        <span>1.0x</span>
        <span>◉</span>
        <span>⛶</span>
      </div>
      <div className="timeline-dots">
        {Array.from({ length: 16 }, (_, index) => <i key={index} />)}
      </div>
    </>
  );
}

export function MiniField({ dense = false }: { dense?: boolean }) {
  const dots = dense ? fieldPlayers : fieldPlayers.slice(0, 8);
  return (
    <div className="mini-field">
      {dots.map(([number, x, y, color]) => (
        <span key={number} className="player-dot" style={{ "--x": x, "--y": y, "--dot": color } as React.CSSProperties}>
          {number}
        </span>
      ))}
    </div>
  );
}

export function HeatMap() {
  const pattern = ["cool", "warm", "hot", "", "warm", "hot", "cool", "", "warm", "hot"];
  return (
    <div className="heatmap">
      {Array.from({ length: 60 }, (_, index) => (
        <i key={index} className={`heat-cell ${pattern[(index + Math.floor(index / 6)) % pattern.length]}`} />
      ))}
    </div>
  );
}

export function TrendLine({ data }: { data: number[] }) {
  const points = data.map((value, index) => `${(index / Math.max(data.length - 1, 1)) * 100},${100 - value}`).join(" ");
  return (
    <div className="chart-box">
      <svg viewBox="0 0 100 100" role="img" aria-label="Trend chart" style={{ width: "100%", height: "100%" }}>
        <polyline points={points} fill="none" stroke="var(--blue)" strokeWidth="3" vectorEffect="non-scaling-stroke" />
        {data.map((value, index) => (
          <circle key={index} cx={(index / Math.max(data.length - 1, 1)) * 100} cy={100 - value} r="2.2" fill="var(--gold)" />
        ))}
      </svg>
    </div>
  );
}

export function PlayerPortrait({ player }: { player: PlayerSummary }) {
  return (
    <div
      style={{
        minHeight: 124,
        borderRadius: 7,
        border: "1px solid var(--line-soft)",
        background: "linear-gradient(135deg, oklch(0.2 0.05 252), oklch(0.33 0.09 252))",
        padding: 14,
        display: "grid",
        alignContent: "end",
      }}
    >
      <strong style={{ fontSize: "2.1rem", lineHeight: 1 }}>#{player.jersey}</strong>
      <span style={{ color: "var(--muted)", fontWeight: 800 }}>{player.position} · {player.name}</span>
    </div>
  );
}
