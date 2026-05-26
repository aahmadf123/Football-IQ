"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Download,
  Filter,
  Pause,
  Search,
  Trash2,
  Upload,
  UserRound,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { FootballShell } from "./football-shell";
import { FieldStage, HeatMap, MiniField, PlayerPortrait, TrendLine, VideoControls } from "./visuals";
import { useAppState, SIDE_LABELS } from "@/lib/app-state";
import { MockBadge } from "@/components/mock-badge";
import type { FootballData, PageKey, PlayerSummary, PlaySummary, TendencyEntry } from "@/lib/types";

export function PageRenderer({ page }: { page: PageKey }) {
  const state = useAppState();
  const { data, addUploads } = state;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const handleUploadClick = () => fileInputRef.current?.click();

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    try {
      const created = await addUploads(files);
      setUploadStatus(`Uploaded ${created.length} clip${created.length === 1 ? "" : "s"} ready for review`);
      setTimeout(() => setUploadStatus(null), 4000);
    } catch (err) {
      setUploadStatus(`Upload failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      // Reset input so the same file can be re-selected
      event.target.value = "";
    }
  };

  return (
    <FootballShell activePage={page}>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="video/*"
        multiple
        style={{ display: "none" }}
      />
      {uploadStatus && (
        <div
          className="upload-toast"
          style={{
            marginBottom: 8,
            padding: "6px 12px",
            borderRadius: 8,
            border: "1px solid var(--line-soft)",
            background: "oklch(0.30 0.10 145 / 0.55)",
            color: "var(--text)",
            fontSize: "0.78rem",
            fontWeight: 700,
          }}
        >
          {uploadStatus}
        </div>
      )}
      {page === "dashboard" && <Dashboard />}
      {page === "video-and-plays" && <VideoAndPlays onUploadClick={handleUploadClick} />}
      {page === "players" && <Players />}
      {page === "analytics" && <Analytics data={data} />}
      {page === "self-scout" && <SelfScout data={data} />}
      {page === "opponent-scout" && <OpponentScout data={data} />}
      {page === "player-development" && <PlayerDevelopment />}
      {page === "health-workload" && <HealthWorkload data={data} />}
      {page === "reports" && <Reports data={data} onUploadClick={handleUploadClick} />}
      {page === "clips-highlights" && <ClipsHighlights />}
      {page === "settings" && <SettingsView data={data} />}
    </FootballShell>
  );
}

function Dashboard() {
  const {
    data,
    sideOfBall,
    filteredPlays,
    currentPlay,
    currentPlayIndex,
    nextPlay,
    prevPlay,
    selectedPlayer,
    setSelectedPlayerId,
    filteredPlayers,
    uploads,
  } = useAppState();

  const totalClipsUploaded = data.videos.length + data.clips.length + uploads.length;
  const playLabel = currentPlay
    ? `Play ${currentPlay.number} · ${currentPlay.formation} · Personnel ${currentPlay.personnel} (${SIDE_LABELS[sideOfBall]})`
    : `No plays for ${SIDE_LABELS[sideOfBall]}`;

  return (
    <div className="dashboard-page content-grid">
      <section className="panel span-8 dash-film">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Practice / Game Film</h2>
            <p className="kicker">{playLabel} · {currentPlayIndex + 1} / {filteredPlays.length || 0} · {totalClipsUploaded} total clips</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="icon-button"
              aria-label="Previous play"
              onClick={prevPlay}
              disabled={filteredPlays.length === 0}
            >
              <ArrowLeft size={16} />
            </button>
            <button
              className="icon-button"
              aria-label="Next play"
              onClick={nextPlay}
              disabled={filteredPlays.length === 0}
            >
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
        <OverlayLayerToggles />
        <FieldStage />
        <VideoControls />
      </section>

      <aside className="span-4 content-grid dash-side">
        <section className="panel panel-pad span-12">
          <h2 className="panel-title">Key Play Metrics</h2>
          <div className="metric-grid" style={{ marginTop: 10 }}>
            <Metric label="Max Speed" value={selectedPlayer ? String(selectedPlayer.maxSpeed) : "—"} unit="MPH" />
            <Metric label="Separation" value={selectedPlayer ? String(selectedPlayer.separation) : "—"} unit="YDS" />
            <Metric label="Yards Gained" value={String(currentPlay?.yards ?? 0)} unit="YDS" />
            <Metric label="Confidence" value={`${Math.round((currentPlay?.confidence ?? 0) * 100)}%`} unit="" />
          </div>
        </section>
        <section className="panel panel-pad span-7">
          <h2 className="panel-title">Player Tracking</h2>
          <div style={{ marginTop: 8 }}><MiniField dense /></div>
        </section>
        <section className="panel panel-pad span-5 dash-result">
          <h2 className="panel-title">Play Result</h2>
          <p className="result-headline">{currentPlay?.result ?? "—"}</p>
          <p className="kicker">{currentPlay ? `${currentPlay.yards} yards` : "Select a play"}</p>
          <hr style={{ borderColor: "var(--line-soft)", margin: "8px 0" }} />
          <MetricLine label="Concept" value={currentPlay?.concept ?? "—"} />
          <MetricLine label="Formation" value={currentPlay?.formation ?? "—"} />
        </section>
      </aside>

      <section className="panel panel-pad span-3 dash-card">
        {selectedPlayer ? (
          <PlayerFocus
            player={selectedPlayer}
            allPlayers={filteredPlayers.length ? filteredPlayers : data.players}
            onSelect={setSelectedPlayerId}
            compact
          />
        ) : (
          <>
            <h2 className="panel-title">Player Focus</h2>
            <p className="kicker" style={{ marginTop: 8 }}>No players yet.</p>
          </>
        )}
      </section>
      <section className="panel panel-pad span-3 dash-card">
        <h2 className="panel-title">Biomechanics <MockBadge status="mock" /></h2>
        {selectedPlayer ? (
          <>
            <PlayerPortrait player={selectedPlayer} compact />
            {/* Sample values — per-player biomechanics wire-up tracked in #100. */}
            <div className="list-stack" style={{ marginTop: 8 }}>
              <MetricLine label="Pad Level" value="-4.2°" />
              <MetricLine label="Torso Angle" value="18.6°" />
              <MetricLine label="Stride Length" value="6.2 ft" />
              <MetricLine label="Symmetry Score" value="92%" />
            </div>
          </>
        ) : (
          <p className="kicker" style={{ marginTop: 8 }}>No players yet.</p>
        )}
      </section>
      <section className="panel panel-pad span-3 dash-card">
        <h2 className="panel-title">Formation Recognition</h2>
        <p className="kicker">{currentPlay?.formation ?? "—"}</p>
        <MiniField />
        <div className="status-pill warning" style={{ marginTop: 8 }}>Motion Detected</div>
      </section>
      <section className="panel panel-pad span-3 dash-card">
        <h2 className="panel-title">Effectiveness Summary</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 10 }}>
          <div className="donut"><div>{filteredPlays.length}<br /><small>Plays</small></div></div>
          <div className="list-stack" style={{ flex: 1, gap: 4 }}>
            <MetricLine label="Great" value={String(filteredPlays.filter((p) => p.confidence > 0.9).length)} />
            <MetricLine label="Good" value={String(filteredPlays.filter((p) => p.confidence > 0.8 && p.confidence <= 0.9).length)} />
            <MetricLine label="Average" value={String(filteredPlays.filter((p) => p.confidence > 0.7 && p.confidence <= 0.8).length)} />
            <MetricLine label="Needs Work" value={String(filteredPlays.filter((p) => p.confidence <= 0.7).length)} />
          </div>
        </div>
      </section>

      <PracticeInbox jobs={data.jobs} />

      <BottomInsights data={data} />
    </div>
  );
}

function PracticeInbox({ jobs }: { jobs: readonly import("@/lib/types").ApiJob[] }) {
  const sameSession = jobs.filter((j) => j.is_same_session || j.pipeline_mode === "same_session");
  const nightly = jobs.filter((j) => !j.is_same_session && j.pipeline_mode !== "same_session");

  const statusColor = (s: string) => {
    if (s === "succeeded") return "var(--accent-green, #4ade80)";
    if (s === "running") return "var(--accent-amber, #fbbf24)";
    if (s === "failed") return "var(--accent-red, #f87171)";
    return "var(--text-muted, #94a3b8)";
  };

  const modeLabel = (j: import("@/lib/types").ApiJob) =>
    j.pipeline_mode === "same_session" || j.is_same_session
      ? "Same-Session"
      : "Nightly";

  const modeBadge = (j: import("@/lib/types").ApiJob) => {
    const label = modeLabel(j);
    const bg = label === "Same-Session"
      ? "oklch(0.65 0.18 145 / 0.25)"
      : "oklch(0.55 0.12 250 / 0.25)";
    return (
      <span
        style={{
          display: "inline-block",
          padding: "1px 6px",
          borderRadius: 4,
          fontSize: "0.65rem",
          fontWeight: 700,
          background: bg,
          color: "var(--text)",
          marginLeft: 6,
        }}
      >
        {label}
      </span>
    );
  };

  const renderJobRow = (j: import("@/lib/types").ApiJob) => (
    <div
      key={j.id}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 0",
        borderBottom: "1px solid var(--line-soft, #333)",
        fontSize: "0.78rem",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: statusColor(j.status),
          flexShrink: 0,
        }}
      />
      <span style={{ flex: 1, fontWeight: 600 }}>
        {j.job_type}
        {modeBadge(j)}
      </span>
      <span style={{ color: statusColor(j.status), fontWeight: 600, textTransform: "capitalize" }}>
        {j.status}
      </span>
    </div>
  );

  return (
    <section className="panel panel-pad span-12">
      <h2 className="panel-title">Practice Inbox — Processing Status</h2>
      <p className="kicker" style={{ marginBottom: 8 }}>
        {sameSession.length} same-session · {nightly.length} nightly
      </p>
      {sameSession.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <h3
            style={{
              fontSize: "0.72rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--accent-green, #4ade80)",
              marginBottom: 4,
            }}
          >
            Same-Session (period-break)
          </h3>
          {sameSession.map(renderJobRow)}
        </div>
      )}
      {nightly.length > 0 && (
        <div>
          <h3
            style={{
              fontSize: "0.72rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--text-muted, #94a3b8)",
              marginBottom: 4,
            }}
          >
            Nightly (full quality)
          </h3>
          {nightly.map(renderJobRow)}
        </div>
      )}
    </section>
  );
}

function OverlayLayerToggles() {
  const [active, setActive] = useState(0);
  const tabs = ["Raw", "Tracks", "Formation", "Wireframe"];
  return (
    <div className="tabs">
      {tabs.map((tab, index) => (
        <button
          key={tab}
          type="button"
          className={`tab-button ${index === active ? "active" : ""}`}
          onClick={() => setActive(index)}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

function VideoAndPlays({ onUploadClick }: { onUploadClick: () => void }) {
  const { data, filteredPlays, currentPlayIndex, setCurrentPlayIndex, uploads, removeUpload } = useAppState();
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
          {filteredPlays.length === 0 && (
            <div className="kicker">No plays match the current filter.</div>
          )}
          {filteredPlays.map((play, i) => (
            <button
              key={play.number}
              type="button"
              className="row-button"
              data-active={i === currentPlayIndex}
              onClick={() => setCurrentPlayIndex(i)}
            >
              <PlayRow play={play} />
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button className="control-button primary"><CheckCircle2 size={15} /> Approve</button>
          <button className="control-button"><Pause size={15} /> Hold for Review</button>
        </div>
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Play List</h2>
        <TableRows data={filteredPlays} onSelect={setCurrentPlayIndex} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Uploaded Clips</h2>
        {uploads.length === 0 ? (
          <div className="kicker" style={{ marginTop: 8 }}>No client uploads yet. Click <strong>Upload Film</strong> to add MP4/MOV files.</div>
        ) : (
          <div className="list-stack" style={{ marginTop: 10 }}>
            {uploads.map((u) => (
              <div key={u.id} className="status-row" style={{ gridTemplateColumns: "1fr auto auto" }}>
                <div>
                  <strong>{u.filename}</strong>
                  <div className="kicker">{(u.sizeBytes / (1024 * 1024)).toFixed(1)} MB · {new Date(u.uploadedAt).toLocaleString()}</div>
                </div>
                {u.objectUrl && (
                  <a className="control-button" href={u.objectUrl} target="_blank" rel="noreferrer">Open</a>
                )}
                <button className="control-button" onClick={() => removeUpload(u.id)} aria-label="Remove upload">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="kicker" style={{ marginTop: 10 }}>
          Library total: {data.videos.length + uploads.length} videos · {data.clips.length} cataloged clips
        </div>
      </section>
    </div>
  );
}

function Players() {
  const { data, filteredPlayers, selectedPlayer, setSelectedPlayerId } = useAppState();
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const list = filteredPlayers.length ? filteredPlayers : data.players;
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.position.toLowerCase().includes(q) ||
        p.jersey.includes(q),
    );
  }, [filteredPlayers, data.players, query]);

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-8">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <h2 className="panel-title">Roster Intelligence</h2>
          <label className="search-inline">
            <Search size={15} />
            <input
              placeholder="Search by name, jersey, or position"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {visible.length === 0 && <div className="kicker">No players match the current filter.</div>}
          {visible.map((player) => (
            <Link
              key={player.id}
              href={`/players/${encodeURIComponent(player.id)}`}
              className="table-row table-row-link"
              onMouseEnter={() => setSelectedPlayerId(player.id)}
            >
              <strong>#{player.jersey} {player.name}</strong>
              <span>{player.position}</span>
              <span>{player.maxSpeed} MPH</span>
              <span>{player.distance} YDS</span>
              <span className="status-pill info">{Math.round(player.confidence * 100)}%</span>
            </Link>
          ))}
        </div>
      </section>
      <section className="panel panel-pad span-4">
        {selectedPlayer ? (
          <>
            <PlayerFocus
              player={selectedPlayer}
              allPlayers={visible.length ? visible : data.players}
              onSelect={setSelectedPlayerId}
            />
            <Link href={`/players/${encodeURIComponent(selectedPlayer.id)}`} className="control-button primary" style={{ marginTop: 12, textDecoration: "none", justifyContent: "center" }}>
              <UserRound size={15} /> Open Full Profile
            </Link>
          </>
        ) : (
          <>
            <h2 className="panel-title">Player Focus</h2>
            <p className="kicker" style={{ marginTop: 8 }}>No players yet.</p>
          </>
        )}
      </section>
      {(visible.length ? visible : data.players).slice(0, 3).map((player) => (
        <section key={player.id} className="panel panel-pad span-4">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 className="panel-title">Trend · #{player.jersey}</h2>
            <Link href={`/players/${encodeURIComponent(player.id)}`} className="link-button">View</Link>
          </div>
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
        <h2 className="panel-title">Key Metrics <MockBadge status="mock" /></h2>
        {/* xSep/xYards/xPressure are not wired to a real model yet — see #102. */}
        <div className="metric-grid" style={{ marginTop: 12 }}>
          <Metric label="Total Plays" value={String(data.plays.length)} unit="" />
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
        <h2 className="panel-title">Model Quality <MockBadge status="mock" /></h2>
        {/* Sample values — surfaced via real model registry in a future change. */}
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

function PlayerDevelopment() {
  const { data, selectedPlayer, setSelectedPlayerId, filteredPlayers } = useAppState();
  const pool = filteredPlayers.length ? filteredPlayers : data.players;
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
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <PlayerFocus player={selectedPlayer} allPlayers={pool} onSelect={setSelectedPlayerId} />
        <Link href={`/players/${encodeURIComponent(selectedPlayer.id)}`} className="control-button primary" style={{ marginTop: 12, textDecoration: "none", justifyContent: "center" }}>
          <UserRound size={15} /> Open Full Profile
        </Link>
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Biomechanics · Pose <MockBadge status="mock" /></h2>
        <PlayerPortrait player={selectedPlayer} />
        {/* Sample values — per-player biomechanics wire-up tracked in #100. */}
        <MetricLine label="Breakpoint angle" value="18.4°" />
        <MetricLine label="Stride symmetry" value="92%" />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Trend Lines</h2>
        <TrendLine data={selectedPlayer.trend} />
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
        <h2 className="panel-title">Team Load Trend <MockBadge status="mock" /></h2>
        {/* Sample trend — real load data lands with the health pipeline. */}
        <TrendLine data={[28, 42, 39, 58, 64, 57, 73, 80]} />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Top Load</h2>
        {data.health.length === 0 ? (
          <p className="kicker" style={{ marginTop: 12 }}>No health data yet.</p>
        ) : (
          <div className="list-stack" style={{ marginTop: 12 }}>
            {data.health.map((item) => <MetricLine key={item.player} label={item.player} value={item.load} />)}
          </div>
        )}
      </section>
      <section className="panel panel-pad span-3">
        <h2 className="panel-title">Readiness <MockBadge status="mock" /></h2>
        {/* Sample readiness — real value sourced from health pipeline. */}
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

function Reports({ data, onUploadClick }: { data: FootballData; onUploadClick: () => void }) {
  const [selections, setSelections] = useState<Record<string, boolean>>({});
  const sections = ["Self-scout exposure", "Position group development", "Model quality", "Opponent prep package"];

  const generate = () => {
    const picked = sections.filter((s) => selections[s] !== false);
    if (picked.length === 0) {
      alert("Select at least one section to include in the report.");
      return;
    }
    const lines = [
      "TOLEDO FOOTBALL IQ — Coaching Report",
      `Generated: ${new Date().toLocaleString()}`,
      "",
      ...picked.map((s) => `- ${s}`),
      "",
      `Total plays: ${data.plays.length}`,
      `Total clips: ${data.clips.length}`,
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `toledo-football-report-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Report Builder</h2>
        {sections.map((label) => (
          <div key={label} className="form-control" style={{ marginTop: 10 }}>
            <label>{label}</label>
            <select
              value={selections[label] === false ? "skip" : "include"}
              onChange={(e) => setSelections((cur) => ({ ...cur, [label]: e.target.value === "include" }))}
            >
              <option value="include">Include in packet</option>
              <option value="skip">Skip this section</option>
            </select>
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button className="control-button primary" onClick={generate}><Download size={15} /> Generate Report</button>
          <button className="control-button" onClick={onUploadClick}><Upload size={15} /> Add Film</button>
        </div>
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Preview</h2>
        <div style={{ minHeight: 270, borderRadius: 7, background: "oklch(0.94 0.01 252)", color: "oklch(0.18 0.04 252)", padding: 22 }}>
          <strong>TOLEDO FOOTBALL IQ</strong>
          <p>Practice intelligence report · {new Date().toLocaleDateString()}</p>
          <hr />
          <p>Top insight: Inside Zone success rate is up 18% this week.</p>
          <p>{data.plays.length} plays · {data.clips.length} clips reviewed</p>
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

function ClipsHighlights() {
  const { data } = useAppState();
  const [filterTag, setFilterTag] = useState<string>("All");
  const [query, setQuery] = useState("");

  const tags = useMemo(() => ["All", ...Array.from(new Set(data.clips.map((c) => c.tag)))], [data.clips]);

  const visibleClips = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.clips.filter((c) => {
      const okTag = filterTag === "All" || c.tag === filterTag;
      const okQuery = !q || c.title.toLowerCase().includes(q) || c.subtitle.toLowerCase().includes(q);
      return okTag && okQuery;
    });
  }, [data.clips, filterTag, query]);

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-8">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <h2 className="panel-title">Clip Library</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Filter size={15} />
            <select value={filterTag} onChange={(e) => setFilterTag(e.target.value)} className="inline-select">
              {tags.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <ClipGrid data={{ ...data, clips: visibleClips }} />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Highlight Builder</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {["Drag clips into order", "Coach review track", "Team celebration", "Share cutup"].map((item, index) => (
            <MetricLine key={item} label={`${index + 1}. ${item}`} value="Ready" />
          ))}
        </div>
        <button className="control-button primary" style={{ marginTop: 12 }} onClick={() => alert(`Reel rendered with ${visibleClips.length} clips`)}>Render Reel</button>
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Search</h2>
        <div className="form-control">
          <label>Find clips</label>
          <input
            placeholder="inside zone, man coverage, #11"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <p className="kicker" style={{ marginTop: 8 }}>{visibleClips.length} of {data.clips.length} clips shown</p>
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Receiving / Player View <MockBadge status="mock" /></h2>
        {/* Counts are illustrative until the player-facing pipeline lands. */}
        <BarList items={[["Approved teaching clips", 12], ["Player-facing summaries", 8], ["Recruiting-ready exports", 4]]} />
      </section>
    </div>
  );
}

function SettingsView({ data }: { data: FootballData }) {
  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">System Config <MockBadge status="mock" /></h2>
        {/* Inputs are not yet wired to a settings endpoint. */}
        {["Team name", "Capture camera", "S3/R2 bucket", "Auto-export access"].map((label) => (
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
        <h2 className="panel-title">Model Sensitivity <MockBadge status="mock" /></h2>
        <BarList items={[["Boundary sensitivity", 68], ["Identity confidence", 82], ["Motion minimum", 72], ["Pose review gate", 88]]} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Pipeline Monitor <MockBadge status="mock" /></h2>
        <TrendLine data={[33, 38, 45, 52, 49, 65, 73]} />
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Integrations</h2>
        {data.jobs.length === 0 ? (
          <p className="kicker" style={{ marginTop: 12 }}>No jobs yet.</p>
        ) : (
          <div className="list-stack" style={{ marginTop: 12 }}>
            {data.jobs.map((job) => <MetricLine key={job.id} label={job.job_type} value={job.status} />)}
          </div>
        )}
      </section>
    </div>
  );
}

function PlayerFocus({
  player,
  allPlayers,
  onSelect,
  compact = false,
}: {
  player: PlayerSummary;
  allPlayers: PlayerSummary[];
  onSelect: (id: string) => void;
  compact?: boolean;
}) {
  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <h2 className="panel-title">Player Focus</h2>
        <select
          className="inline-select"
          value={player.id}
          onChange={(e) => onSelect(e.target.value)}
          aria-label="Choose player"
        >
          {allPlayers.map((p) => (
            <option key={p.id} value={p.id}>#{p.jersey} {p.name}</option>
          ))}
        </select>
      </div>
      <Link href={`/players/${encodeURIComponent(player.id)}`} style={{ textDecoration: "none", color: "inherit", display: "block", marginTop: 6 }}>
        <PlayerPortrait player={player} compact={compact} />
      </Link>
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
          <h2 className="panel-title">Development Alerts <MockBadge status="mock" /></h2>
          {/* Sample alerts — wired to real model output in a later change. */}
          <div className="list-stack" style={{ marginTop: 12 }}>
            <Insight title="#75 RT" detail="Pad level inconsistent" severity="danger" />
            <Insight title="#3 CB" detail="Eyes in backfield on PA" severity="warning" />
          </div>
        </div>
        <div className="span-3">
          <h2 className="panel-title">Workload & Health <MockBadge status="mock" /></h2>
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
    <div className="status-row" style={{ gridTemplateColumns: "34px 1fr auto", border: "none", background: "transparent", padding: 0 }}>
      <strong>{play.number}</strong>
      <span>{play.formation} · {play.concept}</span>
      <span className={play.confidence < 0.7 ? "status-pill warning" : "status-pill"}>{Math.round(play.confidence * 100)}%</span>
    </div>
  );
}

function TableRows({ data, onSelect }: { data: PlaySummary[]; onSelect?: (i: number) => void }) {
  if (data.length === 0) return <div className="kicker" style={{ marginTop: 8 }}>No plays.</div>;
  return (
    <div className="list-stack" style={{ marginTop: 12 }}>
      {data.map((play, i) => (
        <button
          key={play.number}
          type="button"
          className="row-button"
          onClick={() => onSelect?.(i)}
        >
          <div className="table-row" style={{ border: "none", background: "transparent", padding: 0, width: "100%" }}>
            <strong>Play {play.number}</strong>
            <span>{play.formation}</span>
            <span>{play.personnel}</span>
            <span>{play.result}</span>
            <span>{play.yards} YDS</span>
          </div>
        </button>
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
  if (data.clips.length === 0) {
    return <div className="kicker" style={{ marginTop: 12 }}>No clips to display.</div>;
  }
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
