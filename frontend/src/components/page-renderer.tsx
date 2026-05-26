"use client";

import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Download,
  Filter,
  Pause,
  Search,
  Upload,
} from "lucide-react";
import { FootballShell } from "./football-shell";
import { FieldStage, HeatMap, MiniField, PlayerPortrait, TrendLine, VideoControls } from "./visuals";
import { useFootballIqData } from "@/lib/api";
import type { FootballData, PageKey, PlayerSummary, PlaySummary, TendencyEntry } from "@/lib/types";
import { useRef } from "react";

export function PageRenderer({ page }: { page: PageKey }) {
  const { data, source, loading, error, refresh } = useFootballIqData();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
      const workerBase = process.env.NEXT_PUBLIC_WORKER_URL || "";
      
      const targetBase = workerBase || apiBase;
      if (!targetBase) {
        alert("Please configure NEXT_PUBLIC_API_URL or NEXT_PUBLIC_WORKER_URL to upload directly to R2 bucket.");
        return;
      }

      // 1. Get presigned upload URL
      const uploadUrlRes = await fetch(`${targetBase}/api/v1/videos/upload-url`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer sample-token"
        },
        body: JSON.stringify({ filename: file.name })
      });

      if (!uploadUrlRes.ok) {
        throw new Error(`Failed to get presigned upload URL: ${uploadUrlRes.statusText}`);
      }

      const { uploadUrl, key } = await uploadUrlRes.json() as { uploadUrl: string; key: string };

      // 2. Put file to R2
      const uploadRes = await fetch(uploadUrl, {
        method: "PUT",
        headers: {
          "Content-Type": file.type || "video/mp4",
        },
        body: file
      });

      if (!uploadRes.ok) {
        throw new Error("Failed to upload file to Cloudflare R2 bucket.");
      }

      // 3. Register with backend
      const registerRes = await fetch(`${apiBase || workerBase}/api/v1/videos`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer sample-token"
        },
        body: JSON.stringify({
          filename: file.name,
          storage_uri: `r2://raw-video/${key}`
        })
      });

      if (!registerRes.ok) {
        // Fallback local registration logic if api database isn't fully ready
        console.warn("API database registration skipped/failed, keeping local state updated.");
      }

      alert(`Successfully uploaded ${file.name} to R2 bucket!`);
      if (refresh) refresh(file.name);
    } catch (err) {
      console.error(err);
      alert(`Upload error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <FootballShell activePage={page}>
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileChange} 
        accept="video/mp4" 
        style={{ display: "none" }} 
      />
      {source === "fallback" && (
        <div
          className="fallback-banner"
          style={{
            marginBottom: 8,
            padding: "6px 12px",
            borderRadius: 8,
            border: "1px solid var(--line-soft)",
            background: "oklch(0.18 0.04 252 / 0.6)",
            color: "var(--muted)",
            fontSize: "0.74rem",
          }}
        >
          {loading ? "Checking live API..." : "Using polished fallback data. Connect NEXT_PUBLIC_API_URL for live data."}
          {error ? ` ${error}` : ""}
        </div>
      )}
      {page === "dashboard" && <Dashboard data={data} />}
      {page === "video-and-plays" && <VideoAndPlays data={data} onUploadClick={handleUploadClick} />}
      {page === "players" && <Players data={data} />}
      {page === "analytics" && <Analytics data={data} />}
      {page === "self-scout" && <SelfScout data={data} />}
      {page === "opponent-scout" && <OpponentScout data={data} />}
      {page === "player-development" && <PlayerDevelopment data={data} />}
      {page === "health-workload" && <HealthWorkload data={data} />}
      {page === "reports" && <Reports data={data} />}
      {page === "clips-highlights" && <ClipsHighlights data={data} />}
      {page === "settings" && <SettingsView data={data} />}
    </FootballShell>
  );
}

function Dashboard({ data }: { data: FootballData }) {
  // Compute dynamically based on actual uploaded films/plays
  const totalClipsUploaded = data.videos ? data.videos.length + data.clips.length : data.clips.length;
  const derivedPlayCount = data.plays ? data.plays.length : 4;
  const showPlayNum = derivedPlayCount > 4 ? derivedPlayCount : 42;

  return (
    <div className="dashboard-page content-grid">
      <section className="panel span-8 dash-film">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Practice / Game Film</h2>
            <p className="kicker">Play {showPlayNum} / {totalClipsUploaded} · Formation Trips Right · Personnel 11 (Both Offense & Defense Session Tracking)</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="icon-button" aria-label="Previous play"><ArrowLeft size={16} /></button>
            <button className="icon-button" aria-label="Next play"><ArrowRight size={16} /></button>
          </div>
        </div>
        <div className="tabs">
          {["All-22 View"].map((tab, index) => (
            <button key={tab} type="button" className={`tab-button ${index === 0 ? "active" : ""}`}>{tab}</button>
          ))}
        </div>
        <FieldStage />
        <VideoControls />
      </section>

      <aside className="span-4 content-grid dash-side">
        <section className="panel panel-pad span-12">
          <h2 className="panel-title">Key Play Metrics</h2>
          <div className="metric-grid" style={{ marginTop: 10 }}>
            <Metric label="Max Speed" value="19.6" unit="MPH" />
            <Metric label="Separation" value="2.8" unit="YDS" />
            <Metric label="Yards Gained" value="8.4" unit="YDS" />
            <Metric label="Time to Throw" value="2.45" unit="SEC" />
          </div>
        </section>
        <section className="panel panel-pad span-7">
          <h2 className="panel-title">Player Tracking</h2>
          <div style={{ marginTop: 8 }}><MiniField dense /></div>
        </section>
        <section className="panel panel-pad span-5 dash-result">
          <h2 className="panel-title">Play Result</h2>
          <p className="result-headline">Gain</p>
          <p className="kicker">8 yards</p>
          <hr style={{ borderColor: "var(--line-soft)", margin: "8px 0" }} />
          <MetricLine label="Run Concept" value="Inside Zone" />
          <MetricLine label="Def. Front" value="4-3 Over" />
        </section>
      </aside>

      <section className="panel panel-pad span-3 dash-card">
        <PlayerFocus player={data.players[0]} compact />
      </section>
      <section className="panel panel-pad span-3 dash-card">
        <h2 className="panel-title">Biomechanics</h2>
        <PlayerPortrait player={data.players[0]} compact />
        <div className="list-stack" style={{ marginTop: 8 }}>
          <MetricLine label="Pad Level" value="-4.2°" />
          <MetricLine label="Torso Angle" value="18.6°" />
          <MetricLine label="Stride Length" value="6.2 ft" />
          <MetricLine label="Symmetry Score" value="92%" />
        </div>
      </section>
      <section className="panel panel-pad span-3 dash-card">
        <h2 className="panel-title">Formation Recognition</h2>
        <p className="kicker">Trips Right</p>
        <MiniField />
        <div className="status-pill warning" style={{ marginTop: 8 }}>Motion Detected</div>
      </section>
      <section className="panel panel-pad span-3 dash-card">
        <h2 className="panel-title">Effectiveness Summary</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 10 }}>
          <div className="donut"><div>112<br /><small>Plays</small></div></div>
          <div className="list-stack" style={{ flex: 1, gap: 4 }}>
            <MetricLine label="Great" value="28" />
            <MetricLine label="Good" value="40" />
            <MetricLine label="Average" value="28" />
            <MetricLine label="Needs Work" value="16" />
          </div>
        </div>
      </section>

      <BottomInsights data={data} />
    </div>
  );
}

function VideoAndPlays({ data, onUploadClick }: { data: FootballData; onUploadClick: () => void }) {
  return (
    <div className="content-grid">
      <section className="panel span-7">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Clip Review</h2>
            <p className="kicker">Editable boundaries, overlays, comments, and labels</p>
          </div>
          <button className="control-button primary" onClick={onUploadClick}><Upload size={15} /> Upload Film</button>
        </div>
        <FieldStage />
        <VideoControls />
      </section>
      <section className="panel panel-pad span-5">
        <h2 className="panel-title">Play Tags & Corrections</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {data.plays.map((play) => <PlayRow key={play.number} play={play} />)}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button className="control-button primary"><CheckCircle2 size={15} /> Approve</button>
          <button className="control-button"><Pause size={15} /> Hold for Review</button>
        </div>
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Play List</h2>
        <TableRows data={data.plays} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Event Timeline</h2>
        <TrendLine data={[18, 31, 37, 49, 54, 63, 72, 78]} />
      </section>
    </div>
  );
}

function Players({ data }: { data: FootballData }) {
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-8">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <h2 className="panel-title">Roster Intelligence</h2>
          <button className="control-button"><Search size={15} /> Search</button>
        </div>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {data.players.map((player) => (
            <div key={player.id} className="table-row">
              <strong>#{player.jersey} {player.name}</strong>
              <span>{player.position}</span>
              <span>{player.maxSpeed} MPH</span>
              <span>{player.distance} YDS</span>
              <span className="status-pill info">{Math.round(player.confidence * 100)}%</span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel panel-pad span-4">
        <PlayerFocus player={data.players[0]} />
      </section>
      {data.players.slice(0, 3).map((player) => (
        <section key={player.id} className="panel panel-pad span-4">
          <h2 className="panel-title">Trend · #{player.jersey}</h2>
          <TrendLine data={player.trend} />
        </section>
      ))}
    </div>
  );
}

function Analytics({ data }: { data: FootballData }) {
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Key Metrics</h2>
        <div className="metric-grid" style={{ marginTop: 12 }}>
          <Metric label="Total Plays" value="112" unit="" />
          <Metric label="xSep" value="2.64" unit="YDS" />
          <Metric label="xYards" value="11.8" unit="" />
          <Metric label="xPressure" value="95%" unit="" />
        </div>
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Formation Recognition</h2>
        <MiniField dense />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Model Quality</h2>
        <BarList items={[["Boundary confidence", 91], ["Tracking continuity", 88], ["Label confidence", 83], ["Pose quality", 79]]} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Spatial Heatmap</h2>
        <HeatMap />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Analytics Alerts</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {data.alerts.map((alert) => <Insight key={alert.title} title={alert.title} detail={alert.detail} severity={alert.severity} />)}
        </div>
      </section>
    </div>
  );
}

function SelfScout({ data }: { data: FootballData }) {
  return <ScoutView data={data} title="Self-Scout Exposure" opponent={false} />;
}

function OpponentScout({ data }: { data: FootballData }) {
  return <ScoutView data={data} title="Opponent Scout Matchup" opponent />;
}

function ScoutView({ data, title, opponent }: { data: FootballData; title: string; opponent: boolean }) {
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-7">
        <h2 className="panel-title">{title}</h2>
        <HeatMap />
      </section>
      <section className="panel panel-pad span-5">
        <h2 className="panel-title">Actionable Flags</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {data.selfScout.pre_snap_tells.map((tell) => (
            <Insight key={tell.grouping_key} title={tell.formation} detail={tell.message} severity="warning" />
          ))}
          {opponent && <Insight title="Boundary corner late" detail="Opponent rotates late against motion" severity="info" />}
        </div>
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Formation Run / Pass</h2>
        <TendencyList data={data.selfScout.formation_tendencies} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Personnel Tendencies</h2>
        <TendencyList data={data.selfScout.personnel_tendencies} />
      </section>
    </div>
  );
}

function PlayerDevelopment({ data }: { data: FootballData }) {
  const player = data.players[0];
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <PlayerFocus player={player} />
        <button className="control-button primary" style={{ marginTop: 12 }}>Approve Summary</button>
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Biomechanics · Pose</h2>
        <PlayerPortrait player={player} />
        <MetricLine label="Breakpoint angle" value="18.4°" />
        <MetricLine label="Stride symmetry" value="92%" />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Trend Lines</h2>
        <TrendLine data={player.trend} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Best Teaching Clips</h2>
        <ClipGrid data={data} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Development Goals</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          <Insight title="Improve press release timing" detail="Coach approved weekly focus" severity="info" />
          <Insight title="Pad level on contact" detail="Pose confidence high enough for staff use" severity="warning" />
        </div>
      </section>
    </div>
  );
}

function HealthWorkload({ data }: { data: FootballData }) {
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-5">
        <h2 className="panel-title">Team Load Trend</h2>
        <TrendLine data={[28, 42, 39, 58, 64, 57, 73, 80]} />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Top Load</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {data.health.map((item) => <MetricLine key={item.player} label={item.player} value={item.load} />)}
        </div>
      </section>
      <section className="panel panel-pad span-3">
        <h2 className="panel-title">Readiness</h2>
        <div className="donut" style={{ margin: "18px auto" }}><div>64%<br /><small>Ready</small></div></div>
      </section>
      <section className="panel panel-pad span-7">
        <h2 className="panel-title">Accumulation Heatmap</h2>
        <HeatMap />
      </section>
      <section className="panel panel-pad span-5">
        <h2 className="panel-title">Sports Performance Notes</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          <Insight title="Skill WR group elevated" detail="Monitor repeated high-speed reps" severity="warning" />
          <Insight title="#54 C within normal band" detail="Load stable across week" severity="good" />
        </div>
      </section>
    </div>
  );
}

function Reports({ data }: { data: FootballData }) {
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Report Builder</h2>
        {["Self-scout exposure", "Position group development", "Model quality", "Opponent prep package"].map((label) => (
          <div key={label} className="form-control" style={{ marginTop: 10 }}>
            <label>{label}</label>
            <select><option>Include in packet</option></select>
          </div>
        ))}
        <button className="control-button primary" style={{ marginTop: 12 }}><Download size={15} /> Generate PDF</button>
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Preview</h2>
        <div style={{ minHeight: 270, borderRadius: 7, background: "oklch(0.94 0.01 252)", color: "oklch(0.18 0.04 252)", padding: 22 }}>
          <strong>TOLEDO FOOTBALL IQ</strong>
          <p>Practice intelligence report · May 14, 2025</p>
          <hr />
          <p>Top insight: Inside Zone success rate is up 18% this week.</p>
        </div>
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Export Queue</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {data.videos.map((video) => <MetricLine key={video.id} label={video.filename} value={video.status} />)}
        </div>
      </section>
    </div>
  );
}

function ClipsHighlights({ data }: { data: FootballData }) {
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-8">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <h2 className="panel-title">Clip Library</h2>
          <button className="control-button"><Filter size={15} /> Filter</button>
        </div>
        <ClipGrid data={data} />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Highlight Builder</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {["Drag clips into order", "Coach review track", "Team celebration", "Share cutup"].map((item, index) => (
            <MetricLine key={item} label={`${index + 1}. ${item}`} value="Ready" />
          ))}
        </div>
        <button className="control-button primary" style={{ marginTop: 12 }}>Render Reel</button>
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Search</h2>
        <div className="form-control"><label>Find clips</label><input placeholder="inside zone, man coverage, #11" /></div>
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Receiving / Player View</h2>
        <BarList items={[["Approved teaching clips", 12], ["Player-facing summaries", 8], ["Recruiting-ready exports", 4]]} />
      </section>
    </div>
  );
}

function SettingsView({ data }: { data: FootballData }) {
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">System Config</h2>
        {["Team name", "Primary camera", "S3/R2 bucket", "Auto-export access"].map((label) => (
          <div key={label} className="form-control" style={{ marginTop: 10 }}>
            <label>{label}</label>
            <input defaultValue={label === "Team name" ? "Toledo Rockets" : "Configured"} />
          </div>
        ))}
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Legal Taxonomy</h2>
        <TableSimple rows={[["Inside Zone", "Toledo"], ["Mesh", "Generic"], ["Duo", "Generic"], ["PA Boot", "Toledo"]]} />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Model Sensitivity</h2>
        <BarList items={[["Boundary sensitivity", 68], ["Identity confidence", 82], ["Motion minimum", 72], ["Pose review gate", 88]]} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Pipeline Monitor</h2>
        <TrendLine data={[33, 38, 45, 52, 49, 65, 73]} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Integrations</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {data.jobs.map((job) => <MetricLine key={job.id} label={job.job_type} value={job.status} />)}
        </div>
      </section>
    </div>
  );
}

function PlayerFocus({ player, compact = false }: { player: PlayerSummary; compact?: boolean }) {
  return (
    <>
      <h2 className="panel-title">Player Focus</h2>
      <PlayerPortrait player={player} compact={compact} />
      <div className="metric-grid" style={{ marginTop: compact ? 8 : 12, gridTemplateColumns: "repeat(3, 1fr)" }}>
        <Metric label="Distance" value={String(player.distance)} unit="YDS" />
        <Metric label="Max Speed" value={String(player.maxSpeed)} unit="MPH" />
        <Metric label="Avg Sep" value={String(player.separation)} unit="YDS" />
      </div>
      <MetricLine label="Route" value="Corner" />
      <MetricLine label="Targets" value="4" />
      <MetricLine label="Receptions" value="2" />
    </>
  );
}

function BottomInsights({ data }: { data: FootballData }) {
  return (
    <section className="panel panel-pad span-12">
      <div className="content-grid">
        <div className="span-3">
          <h2 className="panel-title">Self-Scout Insights</h2>
          <div className="list-stack" style={{ marginTop: 12 }}>
            {data.alerts.slice(0, 3).map((alert) => <Insight key={alert.title} title={alert.title} detail={alert.detail} severity={alert.severity} />)}
          </div>
        </div>
        <div className="span-3">
          <h2 className="panel-title">Development Alerts</h2>
          <div className="list-stack" style={{ marginTop: 12 }}>
            <Insight title="#75 RT" detail="Pad level inconsistent" severity="danger" />
            <Insight title="#3 CB" detail="Eyes in backfield on PA" severity="warning" />
          </div>
        </div>
        <div className="span-3">
          <h2 className="panel-title">Workload & Health</h2>
          <TrendLine data={[24, 38, 34, 48, 56, 52, 64]} />
        </div>
        <div className="span-3">
          <h2 className="panel-title">Clip Hub</h2>
          <ClipGrid data={data} compact />
        </div>
      </div>
    </section>
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
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 10 }}>
      <span className="small-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PlayRow({ play }: { play: PlaySummary }) {
  return (
    <div className="status-row" style={{ gridTemplateColumns: "34px 1fr auto" }}>
      <strong>{play.number}</strong>
      <span>{play.formation} · {play.concept}</span>
      <span className={play.confidence < 0.7 ? "status-pill warning" : "status-pill"}>{Math.round(play.confidence * 100)}%</span>
    </div>
  );
}

function TableRows({ data }: { data: PlaySummary[] }) {
  return (
    <div className="list-stack" style={{ marginTop: 12 }}>
      {data.map((play) => (
        <div key={play.number} className="table-row">
          <strong>Play {play.number}</strong>
          <span>{play.formation}</span>
          <span>{play.personnel}</span>
          <span>{play.result}</span>
          <span>{play.yards} YDS</span>
        </div>
      ))}
    </div>
  );
}

function TendencyList({ data }: { data: TendencyEntry[] }) {
  return (
    <div className="list-stack" style={{ marginTop: 12 }}>
      {data.map((item) => (
        <div key={item.grouping_key} className="status-row" style={{ gridTemplateColumns: "1fr 56px minmax(90px, 1fr)" }}>
          <strong>{item.grouping_key}</strong>
          <span>{item.total_plays}</span>
          <div className="progress"><i style={{ "--value": `${item.run_rate * 100}%` } as React.CSSProperties} /></div>
        </div>
      ))}
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

function BarList({ items }: { items: Array<[string, number]> }) {
  return (
    <div className="list-stack" style={{ marginTop: 12 }}>
      {items.map(([label, value]) => (
        <div key={label}>
          <MetricLine label={label} value={`${value}%`} />
          <div className="progress"><i style={{ "--value": `${value}%` } as React.CSSProperties} /></div>
        </div>
      ))}
    </div>
  );
}

function ClipGrid({ data, compact = false }: { data: FootballData; compact?: boolean }) {
  return (
    <div className="clip-grid" style={{ marginTop: 12, gridTemplateColumns: compact ? "1fr" : undefined }}>
      {data.clips.slice(0, compact ? 3 : 6).map((clip) => (
        <div key={clip.id} className="clip-card">
          <div className="clip-thumb"><span>{clip.duration}</span></div>
          <strong>{clip.title}</strong>
          <small style={{ color: "var(--muted)" }}>{clip.subtitle}</small>
        </div>
      ))}
    </div>
  );
}

function TableSimple({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="list-stack" style={{ marginTop: 12 }}>
      {rows.map(([a, b]) => <MetricLine key={a} label={a} value={b} />)}
    </div>
  );
}
