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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FootballShell } from "./football-shell";
import { FieldStage, HeatMap, MiniField, PlayerPortrait, TrendLine, VideoControls } from "./visuals";
import { useAppState, SIDE_LABELS, type ApiStatus, type UploadPhase } from "@/lib/app-state";
import {
  createCorrection,
  createReport,
  fetchMetrics,
  getReport,
  getReportDownloadUrl,
  getSystemSettings,
  listReports,
  updateSystemSettings,
  type ApiMetric,
  type VideoInboxItem,
} from "@/lib/api";
import { MockBadge } from "@/components/mock-badge";
import type {
  FootballData,
  PageKey,
  PlayerSummary,
  PlaySummary,
  ReportFormat,
  ReportJob,
  SystemSettingsResponse,
} from "@/lib/types";

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
      setUploadStatus(
        `Uploaded ${created.length} clip${created.length === 1 ? "" : "s"} — open Film Room → Upload / Process Film to start processing.`,
      );
      setTimeout(() => setUploadStatus(null), 5000);
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
            <Metric label="Max Speed" value={fmtMetric(selectedPlayer?.maxSpeed)} unit="MPH" />
            <Metric label="Separation" value={fmtMetric(selectedPlayer?.separation)} unit="YDS" />
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

      <PracticeInboxSection />

      <BottomInsights data={data} />
    </div>
  );
}

function PracticeInboxSection() {
  const { inboxItems, data, mockMode, apiStatus } = useAppState();
  const jobs = data.jobs;

  // Outside mock mode, never substitute a fake job-based view. Distinguish
  // a genuinely empty inbox from "still connecting" or "backend offline" so
  // the UI does not appear successful when the backend has no inbox data or
  // is not reachable.
  if (!mockMode && inboxItems.length === 0) {
    const isLoading = apiStatus === "loading" || apiStatus === "idle";
    const isOffline = apiStatus === "offline";
    return (
      <section className="panel panel-pad span-12">
        <h2 className="panel-title">Practice Inbox — Processing Status</h2>
        <p className="kicker" style={{ marginTop: 6 }}>
          {isLoading
            ? "Connecting to the inbox…"
            : isOffline
              ? "Inbox unavailable — backend is offline."
              : "No videos in the inbox yet. Upload practice or game film to begin processing."}
        </p>
      </section>
    );
  }

  // Mock mode shows the legacy job-based view from sample data.
  if (mockMode || inboxItems.length === 0) {
    const sameSession = jobs.filter((j) => j.is_same_session || j.pipeline_mode === "same_session");
    const nightly = jobs.filter((j) => !j.is_same_session && j.pipeline_mode !== "same_session");

    const statusColor = (s: string) => {
      if (s === "succeeded") return "var(--accent-green, #4ade80)";
      if (s === "running") return "var(--accent-amber, #fbbf24)";
      if (s === "failed") return "var(--accent-red, #f87171)";
      return "var(--text-muted, #94a3b8)";
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
          <span
            style={{
              display: "inline-block",
              padding: "1px 6px",
              borderRadius: 4,
              fontSize: "0.65rem",
              fontWeight: 700,
              background: (j.pipeline_mode === "same_session" || j.is_same_session)
                ? "oklch(0.65 0.18 145 / 0.25)"
                : "oklch(0.55 0.12 250 / 0.25)",
              color: "var(--text)",
              marginLeft: 6,
            }}
          >
            {(j.pipeline_mode === "same_session" || j.is_same_session) ? "Same-Session" : "Nightly"}
          </span>
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
        {jobs.length === 0 && (
          <p className="kicker">No processing jobs yet. Upload video to begin.</p>
        )}
        {sameSession.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <h3 style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent-green, #4ade80)", marginBottom: 4 }}>Same-Session (period-break)</h3>
            {sameSession.map(renderJobRow)}
          </div>
        )}
        {nightly.length > 0 && (
          <div>
            <h3 style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted, #94a3b8)", marginBottom: 4 }}>Nightly (full quality)</h3>
            {nightly.map(renderJobRow)}
          </div>
        )}
      </section>
    );
  }

  // Real backend-backed inbox view
  return (
    <section className="panel panel-pad span-12">
      <h2 className="panel-title">Practice Inbox — Processing Status</h2>
      <p className="kicker" style={{ marginBottom: 8 }}>
        {inboxItems.length} video{inboxItems.length !== 1 ? "s" : ""} in inbox
      </p>
      {inboxItems.map((item) => (
        <InboxVideoRow key={item.video_id} item={item} />
      ))}
    </section>
  );
}

function InboxVideoRow({ item }: { item: VideoInboxItem }) {
  const statusColor = (s: string) => {
    if (s === "ready") return "var(--accent-green, #4ade80)";
    if (s === "processing") return "var(--accent-amber, #fbbf24)";
    if (s === "failed") return "var(--accent-red, #f87171)";
    return "var(--text-muted, #94a3b8)";
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 0",
        borderBottom: "1px solid var(--line-soft, #333)",
        fontSize: "0.78rem",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: statusColor(item.video_status),
          flexShrink: 0,
        }}
      />
      <span style={{ flex: 1, fontWeight: 600 }}>
        {item.filename}
        {item.same_session_job_count > 0 && (
          <span style={{ display: "inline-block", padding: "1px 6px", borderRadius: 4, fontSize: "0.65rem", fontWeight: 700, background: "oklch(0.65 0.18 145 / 0.25)", color: "var(--text)", marginLeft: 6 }}>
            {item.same_session_job_count} same-session
          </span>
        )}
      </span>
      <span style={{ fontSize: "0.72rem", color: "var(--text-muted, #94a3b8)" }}>
        {item.succeeded_jobs}/{item.total_jobs} jobs
        {item.clip_count > 0 && ` · ${item.clip_count} clips`}
        {item.calibration_safe_pct !== null && ` · ${item.calibration_safe_pct}% safe`}
      </span>
      <span style={{ color: statusColor(item.video_status), fontWeight: 600, textTransform: "capitalize" }}>
        {item.video_status}
      </span>
      {item.latest_error_message && (
        <span title={item.latest_error_message} style={{ color: "var(--accent-red, #f87171)", fontSize: "0.7rem", cursor: "help" }}>
          {item.latest_error_stage ?? "Error"}
        </span>
      )}
    </div>
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

function phaseLabel(phase: UploadPhase): string {
  switch (phase) {
    case "idle": return "Queued";
    case "requesting-url": return "Preparing\u2026";
    case "uploading": return "Uploading\u2026";
    case "registering": return "Registering\u2026";
    case "done": return "Complete";
    case "error": return "Failed";
  }
}

function phaseColor(phase: UploadPhase): string {
  switch (phase) {
    case "done": return "var(--accent-green, #4ade80)";
    case "error": return "var(--accent-red, #f87171)";
    case "uploading":
    case "registering":
    case "requesting-url":
      return "var(--accent-amber, #fbbf24)";
    default: return "var(--text-muted, #94a3b8)";
  }
}

export function VideoAndPlays({ onUploadClick }: { onUploadClick: () => void }) {
  const { data, filteredPlays, currentPlayIndex, setCurrentPlayIndex, uploads, removeUpload, retryUpload } = useAppState();
  return (
    <div className="content-grid">
      <section className="panel span-7">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Clip Review <MockBadge status="mock" /></h2>
            <p className="kicker">
              Editable boundaries, overlays, comments, and labels. For real
              backend-backed clip review, open a clip from{" "}
              <Link href="/film-room/?tab=browse" style={{ color: "var(--gold)" }}>Browse Film</Link>.
            </p>
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
              <div key={u.id} className="status-row" style={{ gridTemplateColumns: "1fr auto auto auto" }}>
                <div>
                  <strong>{u.filename}</strong>
                  <div className="kicker">
                    {(u.sizeBytes / (1024 * 1024)).toFixed(1)} MB
                    {" \u00b7 "}{new Date(u.uploadedAt).toLocaleString()}
                    {" \u00b7 "}
                    <span style={{ color: phaseColor(u.phase), fontWeight: 700 }}>
                      {phaseLabel(u.phase)}
                      {u.phase === "uploading" && ` ${u.progress}%`}
                    </span>
                  </div>
                  {u.phase === "uploading" && (
                    <div style={{ height: 3, background: "var(--line-soft, #333)", borderRadius: 2, marginTop: 4 }}>
                      <div style={{ height: "100%", width: `${u.progress}%`, background: "var(--accent-amber, #fbbf24)", borderRadius: 2, transition: "width 0.3s" }} />
                    </div>
                  )}
                  {u.phase === "error" && u.error && (
                    <div className="kicker" style={{ color: "var(--accent-red, #f87171)", marginTop: 2 }}>
                      {u.error}
                    </div>
                  )}
                </div>
                {u.phase === "error" && (
                  <button className="control-button" onClick={() => retryUpload(u.id)} aria-label="Retry upload">
                    Retry
                  </button>
                )}
                {u.objectUrl && u.phase === "done" && (
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
  const { data, filteredPlayers, selectedPlayer, setSelectedPlayerId, playersStatus } = useAppState();
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
          {visible.length === 0 && (
            <div className="kicker">
              {query.trim() ? "No players match the current filter." : rosterEmptyMessage(playersStatus)}
            </div>
          )}
          {visible.map((player) => (
            <Link
              key={player.id}
              href={`/players/${encodeURIComponent(player.id)}`}
              className="table-row table-row-link"
              onMouseEnter={() => setSelectedPlayerId(player.id)}
            >
              <strong>#{player.jersey} {player.name}</strong>
              <span>{player.position}</span>
              <span>{fmtMetric(player.maxSpeed)} MPH</span>
              <span>{fmtMetric(player.distance)} YDS</span>
              <span className="status-pill info">{fmtConfidence(player.confidence)}</span>
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
            <p className="kicker" style={{ marginTop: 8 }}>{rosterEmptyMessage(playersStatus)}</p>
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

function PlayerDevelopment() {
  const { data, selectedPlayer, setSelectedPlayerId, filteredPlayers, authToken } = useAppState();
  const pool = filteredPlayers.length ? filteredPlayers : data.players;
  const [developmentMetrics, setDevelopmentMetrics] = useState<ApiMetric[]>([]);
  const [metricsState, setMetricsState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [correctionState, setCorrectionState] = useState<Record<string, "saving" | "saved" | "error">>({});

  useEffect(() => {
    if (!authToken || !selectedPlayer) {
      setDevelopmentMetrics([]);
      setMetricsState("idle");
      setMetricsError(null);
      return;
    }
    const playerId = selectedPlayer.id;
    let cancelled = false;
    setMetricsState("loading");
    setMetricsError(null);
    Promise.all([
      fetchMetrics({ metric_name: "effort_review_candidate", player_id: playerId, limit: 200 }, authToken),
      fetchMetrics({ metric_name: "pose_body_orientation_proxy", player_id: playerId, limit: 200 }, authToken),
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
  }, [authToken, selectedPlayer?.id]);

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
        <Link href={`/players/${encodeURIComponent(selectedPlayer.id)}`} className="control-button primary" style={{ marginTop: 12, textDecoration: "none", justifyContent: "center" }}>
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
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Best Teaching Clips</h2>
        <ClipGrid data={data} />
      </section>
      <section className="panel panel-pad span-6">
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

const REPORT_SECTIONS: readonly string[] = [
  "Self-scout exposure",
  "Position group development",
  "Model quality",
  "Opponent prep package",
] as const;

const REPORT_POLL_INTERVAL_MS = 2000;
const REPORT_POLL_TIMEOUT_MS = 120_000;

function Reports({ data, onUploadClick }: { data: FootballData; onUploadClick: () => void }) {
  const { authToken } = useAppState();
  const [selections, setSelections] = useState<Record<string, boolean>>({});
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [reports, setReports] = useState<ReportJob[]>([]);
  const [listStatus, setListStatus] = useState<"idle" | "loading" | "error">("idle");
  const [listError, setListError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const pollHandles = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  const refreshList = useCallback(async () => {
    if (!authToken) {
      setReports([]);
      setListStatus("idle");
      setListError(null);
      return;
    }
    setListStatus("loading");
    setListError(null);
    try {
      const items = await listReports(authToken);
      setReports(items);
      setListStatus("idle");
    } catch (err) {
      setListError(err instanceof Error ? err.message : String(err));
      setListStatus("error");
    }
  }, [authToken]);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  // Clean up outstanding polls on unmount.
  useEffect(() => {
    return () => {
      pollHandles.current.forEach((h) => clearTimeout(h));
      pollHandles.current.clear();
    };
  }, []);

  const pollReport = useCallback(
    (reportId: string) => {
      if (!authToken) return;
      const start = Date.now();
      const tick = async () => {
        try {
          const job = await getReport(reportId, authToken);
          setReports((cur) => cur.map((r) => (r.id === reportId ? job : r)));
          if (job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") {
            return;
          }
          if (Date.now() - start > REPORT_POLL_TIMEOUT_MS) return;
          const h = setTimeout(() => {
            pollHandles.current.delete(h);
            void tick();
          }, REPORT_POLL_INTERVAL_MS);
          pollHandles.current.add(h);
        } catch {
          // On a transient error, stop polling — the user can refresh manually.
        }
      };
      void tick();
    },
    [authToken],
  );

  const handleGenerate = async () => {
    if (!authToken) {
      setGenerateError("You must be signed in to generate a report.");
      return;
    }
    const picked = REPORT_SECTIONS.filter((s) => selections[s] !== false);
    if (picked.length === 0) {
      setGenerateError("Select at least one section to include.");
      return;
    }
    setGenerating(true);
    setGenerateError(null);
    try {
      const job = await createReport(
        { report_type: "coaching_summary", format, sections: [...picked] },
        authToken,
      );
      setReports((cur) => [job, ...cur]);
      pollReport(job.id);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (reportId: string) => {
    if (!authToken) return;
    setDownloadingId(reportId);
    try {
      const { download_url } = await getReportDownloadUrl(reportId, authToken);
      window.location.href = download_url;
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : String(err));
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Report Builder</h2>
        {REPORT_SECTIONS.map((label) => (
          <div key={label} className="form-control" style={{ marginTop: 10 }}>
            <label>{label}</label>
            <select
              value={selections[label] === false ? "skip" : "include"}
              onChange={(e) =>
                setSelections((cur) => ({ ...cur, [label]: e.target.value === "include" }))
              }
            >
              <option value="include">Include in packet</option>
              <option value="skip">Skip this section</option>
            </select>
          </div>
        ))}
        <div className="form-control" style={{ marginTop: 10 }}>
          <label>Format</label>
          <select value={format} onChange={(e) => setFormat(e.target.value as ReportFormat)}>
            <option value="pdf">PDF</option>
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button
            className="control-button primary"
            onClick={handleGenerate}
            disabled={generating || !authToken}
          >
            <Download size={15} /> {generating ? "Requesting…" : "Generate Report"}
          </button>
          <button className="control-button" onClick={onUploadClick}>
            <Upload size={15} /> Add Film
          </button>
        </div>
        {!authToken && (
          <p className="kicker" style={{ marginTop: 8 }}>
            Sign in to generate and download reports.
          </p>
        )}
        {generateError && (
          <p className="kicker" style={{ marginTop: 8, color: "var(--danger, crimson)" }}>
            {generateError}
          </p>
        )}
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Preview</h2>
        <div
          style={{
            minHeight: 270,
            borderRadius: 7,
            background: "oklch(0.94 0.01 252)",
            color: "oklch(0.18 0.04 252)",
            padding: 22,
          }}
        >
          <strong>FOOTBALL-IQ COACHING REPORT</strong>
          <p>Generated from live database aggregates</p>
          <hr />
          <p>
            {data.plays.length} plays · {data.clips.length} clips · {data.videos.length} videos in
            current session view
          </p>
          <p className="kicker" style={{ marginTop: 8 }}>
            Sections selected:{" "}
            {REPORT_SECTIONS.filter((s) => selections[s] !== false).join(", ") || "none"}
          </p>
        </div>
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Export Queue</h2>
        {listStatus === "loading" && (
          <p className="kicker" style={{ marginTop: 12 }}>
            Loading reports…
          </p>
        )}
        {listStatus === "error" && (
          <p className="kicker" style={{ marginTop: 12, color: "var(--danger, crimson)" }}>
            {listError ?? "Failed to load reports."}
          </p>
        )}
        {listStatus === "idle" && reports.length === 0 && (
          <p className="kicker" style={{ marginTop: 12 }}>
            No reports yet — pick sections and click Generate.
          </p>
        )}
        {reports.length > 0 && (
          <div className="list-stack" style={{ marginTop: 12 }}>
            {reports.map((report) => (
              <ReportRow
                key={report.id}
                report={report}
                downloading={downloadingId === report.id}
                onDownload={() => handleDownload(report.id)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ReportRow({
  report,
  downloading,
  onDownload,
}: {
  report: ReportJob;
  downloading: boolean;
  onDownload: () => void;
}) {
  const stamp = new Date(report.created_at).toLocaleString();
  const subtitle =
    report.status === "failed" && report.error_message
      ? `failed: ${report.error_message}`
      : `${report.format.toUpperCase()} · ${stamp}`;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 8,
        padding: "8px 4px",
        borderBottom: "1px solid var(--line-soft)",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: "0.85rem" }}>{report.status}</div>
        <div
          className="kicker"
          style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {subtitle}
        </div>
      </div>
      {report.status === "succeeded" ? (
        <button className="control-button" onClick={onDownload} disabled={downloading}>
          <Download size={13} /> {downloading ? "…" : "Download"}
        </button>
      ) : (
        <span className="kicker">{report.status === "failed" ? "—" : "in progress"}</span>
      )}
    </div>
  );
}

export function ClipsHighlights() {
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
        <h2 className="panel-title">Highlight Builder <MockBadge status="mock" /></h2>
        {/* Reel/cutup workflow lands with a later iteration of #100 — UI
            shown for layout only, not backed by a real builder yet. */}
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
  const { authToken } = useAppState();
  const [settings, setSettings] = useState<SystemSettingsResponse | null>(null);
  const [draft, setDraft] = useState<SystemSettingsResponse | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState<null | "system_config" | "model_sensitivity">(null);
  const [saveErrors, setSaveErrors] = useState<{
    system_config: string | null;
    model_sensitivity: string | null;
  }>({ system_config: null, model_sensitivity: null });
  const [savedSection, setSavedSection] = useState<null | "system_config" | "model_sensitivity">(
    null,
  );
  const savedIndicatorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (savedIndicatorTimeoutRef.current) {
        clearTimeout(savedIndicatorTimeoutRef.current);
        savedIndicatorTimeoutRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!authToken) {
      setSettings(null);
      setDraft(null);
      setLoadState("idle");
      setLoadError(null);
      setSaving(null);
      setSaveErrors({ system_config: null, model_sensitivity: null });
      setSavedSection(null);
      if (savedIndicatorTimeoutRef.current) {
        clearTimeout(savedIndicatorTimeoutRef.current);
        savedIndicatorTimeoutRef.current = null;
      }
      return;
    }
    let cancelled = false;
    setLoadState("loading");
    setLoadError(null);
    getSystemSettings(authToken)
      .then((s) => {
        if (cancelled) return;
        setSettings(s);
        setDraft(s);
        setLoadState("idle");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [authToken]);

  const save = async (section: "system_config" | "model_sensitivity") => {
    if (!authToken || !draft) return;
    setSaving(section);
    setSaveErrors((cur) => ({ ...cur, [section]: null }));
    setSavedSection(null);
    if (savedIndicatorTimeoutRef.current) {
      clearTimeout(savedIndicatorTimeoutRef.current);
      savedIndicatorTimeoutRef.current = null;
    }
    try {
      const updated = await updateSystemSettings({ [section]: draft[section] }, authToken);
      setSettings(updated);
      setDraft(updated);
      setSavedSection(section);
      savedIndicatorTimeoutRef.current = setTimeout(
        () => setSavedSection((cur) => (cur === section ? null : cur)),
        2500,
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setSaveErrors((cur) => ({ ...cur, [section]: msg }));
    } finally {
      setSaving(null);
    }
  };

  const updateSystemConfig = <K extends keyof SystemSettingsResponse["system_config"]>(
    key: K,
    value: SystemSettingsResponse["system_config"][K],
  ) => {
    setDraft((cur) =>
      cur ? { ...cur, system_config: { ...cur.system_config, [key]: value } } : cur,
    );
  };

  const updateSensitivity = <K extends keyof SystemSettingsResponse["model_sensitivity"]>(
    key: K,
    value: SystemSettingsResponse["model_sensitivity"][K],
  ) => {
    setDraft((cur) =>
      cur ? { ...cur, model_sensitivity: { ...cur.model_sensitivity, [key]: value } } : cur,
    );
  };

  const systemDirty =
    settings != null &&
    draft != null &&
    JSON.stringify(settings.system_config) !== JSON.stringify(draft.system_config);
  const sensitivityDirty =
    settings != null &&
    draft != null &&
    JSON.stringify(settings.model_sensitivity) !== JSON.stringify(draft.model_sensitivity);

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">System Config</h2>
        {loadState === "loading" && (
          <p className="kicker" style={{ marginTop: 12 }}>
            Loading settings…
          </p>
        )}
        {loadState === "error" && (
          <p className="kicker" style={{ marginTop: 12, color: "var(--danger, crimson)" }}>
            {loadError ?? "Failed to load settings."}
          </p>
        )}
        {!authToken && (
          <p className="kicker" style={{ marginTop: 12 }}>
            Sign in to view and edit system settings.
          </p>
        )}
        {draft && (
          <>
            <div className="form-control" style={{ marginTop: 10 }}>
              <label>Team name</label>
              <input
                value={draft.system_config.team_name}
                maxLength={120}
                onChange={(e) => updateSystemConfig("team_name", e.target.value)}
              />
            </div>
            <div className="form-control" style={{ marginTop: 10 }}>
              <label>Capture camera</label>
              <input
                value={draft.system_config.capture_camera}
                maxLength={120}
                onChange={(e) => updateSystemConfig("capture_camera", e.target.value)}
              />
            </div>
            <div className="form-control" style={{ marginTop: 10 }}>
              <label>S3/R2 bucket (display only)</label>
              <input
                value={draft.system_config.storage_bucket}
                maxLength={120}
                onChange={(e) => updateSystemConfig("storage_bucket", e.target.value)}
              />
            </div>
            <div className="form-control" style={{ marginTop: 10 }}>
              <label>Auto-export access</label>
              <select
                value={draft.system_config.auto_export_access}
                onChange={(e) =>
                  updateSystemConfig(
                    "auto_export_access",
                    e.target.value as SystemSettingsResponse["system_config"]["auto_export_access"],
                  )
                }
              >
                <option value="off">Off</option>
                <option value="staff">Staff</option>
                <option value="all">All users</option>
              </select>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
              <button
                className="control-button primary"
                onClick={() => save("system_config")}
                disabled={!systemDirty || saving === "system_config"}
              >
                {saving === "system_config" ? "Saving…" : "Save"}
              </button>
              {savedSection === "system_config" && (
                <span className="kicker" style={{ color: "var(--ok, seagreen)" }}>
                  Saved
                </span>
              )}
            </div>
            {saveErrors.system_config && (
              <p className="kicker" style={{ marginTop: 8, color: "var(--danger, crimson)" }}>
                {saveErrors.system_config}
              </p>
            )}
          </>
        )}
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Legal Taxonomy</h2>
        <TableSimple rows={[["Inside Zone", "Toledo"], ["Mesh", "Generic"], ["Duo", "Generic"], ["PA Boot", "Toledo"]]} />
      </section>
      <section className="panel panel-pad span-4">
        <h2 className="panel-title">Model Sensitivity</h2>
        {draft && (
          <>
            {(
              [
                ["boundary_sensitivity", "Boundary sensitivity"],
                ["identity_confidence", "Identity confidence"],
                ["motion_minimum", "Motion minimum"],
                ["pose_review_gate", "Pose review gate"],
              ] as const
            ).map(([key, label]) => (
              <div key={key} className="form-control" style={{ marginTop: 10 }}>
                <label>
                  {label} ({draft.model_sensitivity[key]})
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={draft.model_sensitivity[key]}
                  onChange={(e) => updateSensitivity(key, Number(e.target.value))}
                />
              </div>
            ))}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
              <button
                className="control-button primary"
                onClick={() => save("model_sensitivity")}
                disabled={!sensitivityDirty || saving === "model_sensitivity"}
              >
                {saving === "model_sensitivity" ? "Saving…" : "Save"}
              </button>
              {savedSection === "model_sensitivity" && (
                <span className="kicker" style={{ color: "var(--ok, seagreen)" }}>
                  Saved
                </span>
              )}
            </div>
          </>
        )}
        {saveErrors.model_sensitivity && (
          <p className="kicker" style={{ marginTop: 8, color: "var(--danger, crimson)" }}>
            {saveErrors.model_sensitivity}
          </p>
        )}
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
        <Metric label="Distance" value={fmtMetric(player.distance)} unit="YDS" />
        <Metric label="Max Speed" value={fmtMetric(player.maxSpeed)} unit="MPH" />
        <Metric label="Avg Sep" value={fmtMetric(player.separation)} unit="YDS" />
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

// Render an optional numeric metric as a string. Metrics that aren't wired to
// the live backend yet (max speed, separation, distance) are surfaced as a
// dash rather than fabricated zeros — see Issue #103 acceptance criteria.
function fmtMetric(value: number | undefined): string {
  return value == null ? "—" : String(value);
}

function fmtConfidence(value: number | undefined): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
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

function rosterEmptyMessage(status: ApiStatus): string {
  switch (status) {
    case "loading":
      return "Loading roster…";
    case "offline":
      return "Roster unavailable — could not reach /api/v1/players.";
    case "live":
      return "Roster is empty. Add players from Settings to populate this view.";
    case "mock":
      return "No players yet.";
    default:
      return "No players yet.";
  }
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
