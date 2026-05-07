"use client";

import { useMemo, useState } from "react";

type SessionStatus = "Processing" | "Failed" | "QA Flag" | "Ready";
type QueuePriority = "Review now" | "Needs analyst" | "Monitor";
type ReviewAction = "approve" | "reject" | "flag";

// ── Head-orientation sample data ──────────────────────────────────────────────

// QB progression-read frames: yaw angle per dropback phase
const qbProgressionData = [
  {
    phase: "Pre-snap",
    targetDescription: "Cover shell — safety alignment",
    yawDegrees: 12,
    confidence: 0.88,
    clip: "Clip 144",
  },
  {
    phase: "1st read window",
    targetDescription: "Primary receiver (Z)",
    yawDegrees: -34,
    confidence: 0.82,
    clip: "Clip 144",
  },
  {
    phase: "2nd read window",
    targetDescription: "Check-down (RB)",
    yawDegrees: 21,
    confidence: 0.79,
    clip: "Clip 144",
  },
  {
    phase: "Release",
    targetDescription: "Check-down (RB) — stare-down detected",
    yawDegrees: 19,
    confidence: 0.76,
    clip: "Clip 144",
  },
];

// LB / Safety play-action response metrics
const playActionData = [
  {
    position: "MLB #45 Carter",
    latencySeconds: 0.41,
    firstStepCorrect: false,
    note: "Triggered on fake — stepped toward LOS",
    confidence: 0.84,
    clip: "Clip 088",
  },
  {
    position: "FS #21 Norris",
    latencySeconds: 0.28,
    firstStepCorrect: false,
    note: "Vacated deep coverage before establishing pass depth",
    confidence: 0.77,
    clip: "Clip 088",
  },
  {
    position: "WLB #52 Wade",
    latencySeconds: 0.56,
    firstStepCorrect: true,
    note: "Correct depth-hold before committing",
    confidence: 0.91,
    clip: "Clip 203",
  },
];

// CB technique samples
const cbTechniqueData = [
  {
    player: "CB #3 Hill",
    coverage: "Man",
    headTracking: "Receiver",
    correct: true,
    note: "Eyes on receiver — correct man technique",
    confidence: 0.86,
    clip: "Clip 144",
  },
  {
    player: "CB #24 Ellis",
    coverage: "Zone",
    headTracking: "Single receiver",
    correct: false,
    note: "Locked on #1, missed route distribution",
    confidence: 0.81,
    clip: "Clip 167",
  },
  {
    player: "CB #3 Hill",
    coverage: "Zone",
    headTracking: "QB + routes",
    correct: true,
    note: "Scanning QB and route distribution — correct zone keys",
    confidence: 0.89,
    clip: "Clip 203",
  },
];

// ── Static data ───────────────────────────────────────────────────────────────

const practiceInbox = [
  {
    session: "Inside Run — Team Period",
    date: "2026-05-07",
    type: "Practice",
    source: "Endzone",
    status: "Processing" as SessionStatus,
    clips: 26,
    failedJob: "Track stitching",
    qaFlag: "Boundary drift on rep 9",
    calibration: 0.93,
  },
  {
    session: "3rd Down — Red Zone",
    date: "2026-05-06",
    type: "Scrimmage",
    source: "Sideline",
    status: "Failed" as SessionStatus,
    clips: 14,
    failedJob: "Overlay render",
    qaFlag: "HLS manifest missing",
    calibration: 0.61,
  },
  {
    session: "PAT / Field Goal",
    date: "2026-05-05",
    type: "Practice",
    source: "Drone",
    status: "QA Flag" as SessionStatus,
    clips: 11,
    failedJob: "None",
    qaFlag: "2 roster conflicts",
    calibration: 0.72,
  },
  {
    session: "Two-Minute Team",
    date: "2026-05-04",
    type: "Game",
    source: "Endzone",
    status: "Ready" as SessionStatus,
    clips: 19,
    failedJob: "None",
    qaFlag: "Clear",
    calibration: 0.88,
  },
];

const clipLabels = [
  { label: "Formation", value: "Trips Right", confidence: 0.94 },
  { label: "Motion", value: "Jet", confidence: 0.82 },
  { label: "Route", value: "Glance", confidence: 0.79 },
  { label: "Coverage", value: "Cover 3 Buzz", confidence: 0.74 },
];

const rosterAssignments = [
  { track: "Track 4", current: "WR #11 Brooks", suggested: "WR #2 Lewis" },
  { track: "Track 7", current: "RB #22 Harmon", suggested: "RB #22 Harmon" },
  { track: "Track 9", current: "TE #88 Small", suggested: "TE #18 Moore" },
];

const tendencyData = [
  { label: "Trips Right", value: 68, clip: "12:44 Q2" },
  { label: "2x2 Gun", value: 51, clip: "09:22 Q3" },
  { label: "Bunch Left", value: 37, clip: "04:18 Q4" },
];

const effortMetrics = [
  { metric: "Sprint-to-ball", value: "83%", evidence: "Clip 144" },
  { metric: "Downfield blocking", value: "71%", evidence: "Clip 088" },
  { metric: "Formation speed", value: "12.4s", evidence: "Clip 203" },
  { metric: "Return-to-huddle", value: "18.2s", evidence: "Clip 167" },
];

const practiceTempo = [
  { metric: "Rep count by period", value: "18 / 21 / 16", evidence: "Period cutup" },
  { metric: "Time between plays", value: "27.4s avg", evidence: "Tempo sample" },
  { metric: "Substitution delays", value: "4 flagged", evidence: "Delay queue" },
];

const labelingQueue = [
  {
    play: "Clip 144",
    issue: "Low-confidence coverage label",
    detail: "Cover 3 Buzz vs Match",
    priority: "Review now" as QueuePriority,
  },
  {
    play: "Clip 088",
    issue: "Identity conflict",
    detail: "Tracklet matched to two WRs",
    priority: "Needs analyst" as QueuePriority,
  },
  {
    play: "Clip 203",
    issue: "Boundary error",
    detail: "Whistle trimmed 1.2s early",
    priority: "Review now" as QueuePriority,
  },
  {
    play: "Clip 167",
    issue: "Model regression example",
    detail: "Motion label changed after model v0.3.8",
    priority: "Monitor" as QueuePriority,
  },
];

const correctionAnalytics = [
  { label: "Coverage", corrections: 23, note: "Most often swapped between Cover 3 and Match" },
  { label: "Motion", corrections: 16, note: "Orbit vs Jet confusion" },
  { label: "Player identity", corrections: 11, note: "Slot / wing alignments need roster review" },
];

const permissions = {
  admin: "All access",
  analyst: "Full correction + export",
  coach: "Clip review + label correction",
  sportsperformance: "Workload and health views in Phase 3",
  player: "Development profile view in Phase 3",
  viewer: "Read-only clips and dashboards",
} as const;

type Role = keyof typeof permissions;

const styles = {
  page: {
    minHeight: "100vh",
    background: "#f4f6f8",
    color: "#102033",
    fontFamily: "Inter, system-ui, sans-serif",
  },
  shell: {
    maxWidth: "1440px",
    margin: "0 auto",
    padding: "32px 24px 64px",
    display: "grid",
    gap: "24px",
  },
  hero: {
    background: "#ffffff",
    border: "1px solid #d6dde5",
    borderRadius: "20px",
    padding: "28px",
    boxShadow: "0 16px 40px rgba(16, 32, 51, 0.08)",
    display: "grid",
    gap: "20px",
  },
  heroRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    justifyContent: "space-between",
    gap: "16px",
    alignItems: "center",
  },
  metricGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: "12px",
  },
  metricCard: {
    padding: "16px",
    borderRadius: "16px",
    border: "1px solid #d6dde5",
    background: "#f8fafc",
  },
  nav: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "10px",
  },
  navLink: {
    padding: "10px 14px",
    borderRadius: "999px",
    background: "#0d4b82",
    color: "#ffffff",
    textDecoration: "none",
    fontSize: "0.95rem",
    fontWeight: 600,
  },
  section: {
    background: "#ffffff",
    border: "1px solid #d6dde5",
    borderRadius: "20px",
    padding: "24px",
    display: "grid",
    gap: "20px",
  },
  sectionHeader: {
    display: "flex",
    flexWrap: "wrap" as const,
    justifyContent: "space-between",
    gap: "16px",
    alignItems: "center",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: "16px",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse" as const,
  },
  tableCell: {
    textAlign: "left" as const,
    padding: "14px 12px",
    borderBottom: "1px solid #e6ebf0",
    verticalAlign: "top" as const,
  },
  playerStage: {
    minHeight: "320px",
    borderRadius: "18px",
    background:
      "linear-gradient(180deg, #0f5132 0%, #166534 60%, #0b3d26 100%)",
    color: "#ffffff",
    padding: "20px",
    position: "relative" as const,
    overflow: "hidden",
    display: "grid",
    alignContent: "space-between",
  },
  overlayGrid: {
    position: "absolute" as const,
    inset: "16px",
    border: "1px solid rgba(255,255,255,0.3)",
    borderRadius: "12px",
    backgroundImage:
      "linear-gradient(to right, rgba(255,255,255,0.12) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.12) 1px, transparent 1px)",
    backgroundSize: "12.5% 20%",
    pointerEvents: "none" as const,
  },
  tracks: {
    display: "flex",
    gap: "10px",
    flexWrap: "wrap" as const,
  },
  playerDot: {
    width: "46px",
    height: "46px",
    borderRadius: "999px",
    background: "rgba(255,255,255,0.18)",
    border: "2px solid rgba(255,255,255,0.45)",
    display: "grid",
    placeItems: "center" as const,
    fontWeight: 700,
  },
  chipRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "8px",
  },
  card: {
    border: "1px solid #d6dde5",
    borderRadius: "16px",
    padding: "16px",
    background: "#f8fafc",
    display: "grid",
    gap: "10px",
  },
  buttonRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "10px",
  },
  button: {
    border: "none",
    borderRadius: "10px",
    padding: "10px 14px",
    background: "#0d4b82",
    color: "#ffffff",
    fontWeight: 600,
    cursor: "pointer",
  },
  secondaryButton: {
    border: "1px solid #c4cfda",
    borderRadius: "10px",
    padding: "10px 14px",
    background: "#ffffff",
    color: "#102033",
    fontWeight: 600,
    cursor: "pointer",
  },
  progressTrack: {
    height: "10px",
    borderRadius: "999px",
    background: "#e3e8ee",
    overflow: "hidden",
  },
  footerNote: {
    color: "#546273",
    fontSize: "0.92rem",
  },
} as const;

function toneColor(value: number) {
  if (value >= 0.85) {
    return "#1c7c54";
  }

  if (value >= 0.7) {
    return "#b7791f";
  }

  return "#b42318";
}

function badgeStyle(background: string, color = "#102033") {
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    padding: "6px 10px",
    borderRadius: "999px",
    background,
    color,
    fontSize: "0.85rem",
    fontWeight: 700,
  };
}

function statusBadge(status: SessionStatus) {
  if (status === "Ready") {
    return badgeStyle("#d9fbe8", "#166534");
  }

  if (status === "Processing") {
    return badgeStyle("#dbeafe", "#1d4ed8");
  }

  if (status === "QA Flag") {
    return badgeStyle("#fef3c7", "#92400e");
  }

  return badgeStyle("#fee2e2", "#b42318");
}

function priorityBadge(priority: QueuePriority) {
  if (priority === "Review now") {
    return badgeStyle("#fee2e2", "#b42318");
  }

  if (priority === "Needs analyst") {
    return badgeStyle("#fef3c7", "#92400e");
  }

  return badgeStyle("#e2e8f0", "#334155");
}

export default function Home() {
  const [role, setRole] = useState<Role>("coach");
  const [clipStart, setClipStart] = useState(8);
  const [clipEnd, setClipEnd] = useState(18);
  const [selectedPlayer, setSelectedPlayer] = useState(rosterAssignments[0].suggested);
  const [showHeadOrientationOverlay, setShowHeadOrientationOverlay] = useState(false);
  const [headOrientationReview, setHeadOrientationReview] = useState<ReviewAction | null>(null);

  const isPlayerRole = role === "player";

  const visiblePermissions = useMemo(
    () =>
      Object.entries(permissions).map(([key, value]) => ({
        key,
        value,
        active: key === role,
      })),
    [role],
  );

  return (
    <main style={styles.page}>
      <div style={styles.shell}>
        <section style={styles.hero}>
          <div style={styles.heroRow}>
            <div>
              <p style={{ margin: 0, color: "#0d4b82", fontWeight: 700 }}>
                Phase 1 MVP dashboard UI
              </p>
              <h1 style={{ margin: "6px 0 10px", fontSize: "2.35rem" }}>
                Boring, fast, coach-centered workflows
              </h1>
              <p style={{ margin: 0, maxWidth: "900px", color: "#546273", lineHeight: 1.6 }}>
                Practice inbox, clip review, coach dashboards, and a labeling queue
                built to surface evidence quickly and keep corrections easy.
              </p>
            </div>
            <label style={{ display: "grid", gap: "6px", fontWeight: 600 }}>
              Viewing as
              <select
                value={role}
                onChange={(event) => setRole(event.target.value as Role)}
                style={{
                  minWidth: "220px",
                  borderRadius: "12px",
                  border: "1px solid #c4cfda",
                  padding: "10px 12px",
                  background: "#ffffff",
                }}
              >
                {Object.keys(permissions).map((permissionRole) => (
                  <option key={permissionRole} value={permissionRole}>
                    {permissionRole}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div style={styles.metricGrid}>
            {[
              ["Sessions in review", "8"],
              ["Failed jobs", "2"],
              ["Low-confidence clips", "11"],
              ["Exports pending", "3"],
            ].map(([label, value]) => (
              <div key={label} style={styles.metricCard}>
                <div style={{ color: "#546273", fontSize: "0.9rem" }}>{label}</div>
                <div style={{ fontSize: "1.8rem", fontWeight: 800 }}>{value}</div>
              </div>
            ))}
          </div>

          <div style={styles.nav}>
            <a href="#practice-inbox" style={styles.navLink}>
              Practice Inbox
            </a>
            <a href="#clip-review" style={styles.navLink}>
              Clip Review
            </a>
            <a href="#coach-dashboards" style={styles.navLink}>
              Coach Dashboards
            </a>
            <a href="#labeling-queue" style={styles.navLink}>
              Labeling Queue
            </a>
            {!isPlayerRole && (
              <a href="#head-orientation" style={{ ...styles.navLink, background: "#6b21a8" }}>
                Head Orientation ⚗
              </a>
            )}
          </div>

          <div style={styles.chipRow}>
            {visiblePermissions.map(({ key, value, active }) => (
              <span
                key={key}
                style={badgeStyle(active ? "#0d4b82" : "#eaf0f5", active ? "#ffffff" : "#102033")}
              >
                {key}: {value}
              </span>
            ))}
          </div>
        </section>

        <section id="practice-inbox" style={styles.section}>
          <div style={styles.sectionHeader}>
            <div>
              <h2 style={{ margin: 0 }}>1. Practice Inbox</h2>
              <p style={{ margin: "6px 0 0", color: "#546273" }}>
                Uploaded sessions, processing state, QA warnings, calibration confidence,
                and one-tap retries for failed jobs.
              </p>
            </div>
            <div style={styles.buttonRow}>
              <button type="button" style={styles.secondaryButton}>
                Filter by session type
              </button>
              <button type="button" style={styles.secondaryButton}>
                Filter by source
              </button>
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={styles.table}>
              <thead>
                <tr>
                  {[
                    "Session",
                    "Date",
                    "Session Type",
                    "Source",
                    "Processing",
                    "Detected Clips",
                    "Calibration",
                    "QA / Failure",
                    "Action",
                  ].map((heading) => (
                    <th key={heading} style={styles.tableCell}>
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {practiceInbox.map((session) => (
                  <tr key={session.session}>
                    <td style={styles.tableCell}>
                      <strong>{session.session}</strong>
                    </td>
                    <td style={styles.tableCell}>{session.date}</td>
                    <td style={styles.tableCell}>{session.type}</td>
                    <td style={styles.tableCell}>{session.source}</td>
                    <td style={styles.tableCell}>
                      <span style={statusBadge(session.status)}>{session.status}</span>
                    </td>
                    <td style={styles.tableCell}>{session.clips}</td>
                    <td style={styles.tableCell}>
                      <div style={{ display: "grid", gap: "8px", minWidth: "160px" }}>
                        <strong style={{ color: toneColor(session.calibration) }}>
                          {(session.calibration * 100).toFixed(0)}%
                        </strong>
                        <div style={styles.progressTrack}>
                          <div
                            style={{
                              width: `${session.calibration * 100}%`,
                              height: "100%",
                              background: toneColor(session.calibration),
                            }}
                          />
                        </div>
                        {session.calibration < 0.75 && (
                          <span style={badgeStyle("#fef3c7", "#92400e")}>
                            Confidence warning
                          </span>
                        )}
                      </div>
                    </td>
                    <td style={styles.tableCell}>
                      <div style={{ display: "grid", gap: "4px" }}>
                        <span>{session.qaFlag}</span>
                        <span style={{ color: "#546273" }}>
                          Failed stage: {session.failedJob}
                        </span>
                      </div>
                    </td>
                    <td style={styles.tableCell}>
                      <button type="button" style={styles.button}>
                        {session.status === "Failed" ? "Retry failed job" : "Open session"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section id="clip-review" style={styles.section}>
          <div style={styles.sectionHeader}>
            <div>
              <h2 style={{ margin: 0 }}>2. Clip Review</h2>
              <p style={{ margin: "6px 0 0", color: "#546273" }}>
                Review overlays, drag clip boundaries, fix identities, log one-click
                corrections, and export evidence clips.
              </p>
            </div>
            <div style={styles.buttonRow}>
              <button type="button" style={styles.button}>
                Export clip
              </button>
              <button type="button" style={styles.secondaryButton}>
                Export clip list
              </button>
            </div>
          </div>

          <div style={styles.grid}>
            <div style={{ display: "grid", gap: "16px" }}>
              <div style={styles.playerStage}>
                <div style={styles.overlayGrid} />
                <div style={styles.chipRow}>
                  <span style={badgeStyle("rgba(255,255,255,0.18)", "#ffffff")}>Field grid</span>
                  <span style={badgeStyle("rgba(255,255,255,0.18)", "#ffffff")}>Player tracks</span>
                  <span style={badgeStyle("rgba(255,255,255,0.18)", "#ffffff")}>Labels + metrics</span>
                  {!isPlayerRole && (
                    <button
                      type="button"
                      onClick={() => setShowHeadOrientationOverlay((v) => !v)}
                      style={{
                        border: "none",
                        borderRadius: "999px",
                        padding: "6px 10px",
                        background: showHeadOrientationOverlay
                          ? "rgba(167,139,250,0.8)"
                          : "rgba(255,255,255,0.18)",
                        color: "#ffffff",
                        fontSize: "0.85rem",
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      {showHeadOrientationOverlay ? "▶ Head direction ON" : "Head direction OFF"}
                    </button>
                  )}
                </div>

                {/* Head-direction arrow overlay (staff only, experimental) */}
                {showHeadOrientationOverlay && !isPlayerRole && (
                  <div
                    style={{
                      position: "absolute",
                      top: "50%",
                      left: "30%",
                      transform: `translate(-50%, -50%) rotate(${qbProgressionData[1].yawDegrees}deg)`,
                      pointerEvents: "none",
                    }}
                  >
                    <svg width="48" height="48" viewBox="0 0 48 48">
                      <line
                        x1="24" y1="40" x2="24" y2="8"
                        stroke="#a78bfa" strokeWidth="3" strokeLinecap="round"
                      />
                      <polygon points="24,4 18,14 30,14" fill="#a78bfa" />
                    </svg>
                  </div>
                )}

                <div>
                  <div style={{ fontSize: "1.15rem", fontWeight: 700 }}>Clip 144 — 3rd & 6</div>
                  <p style={{ margin: "6px 0 0", maxWidth: "460px", lineHeight: 1.5 }}>
                    Overlay-ready player view with formation landmarks, track IDs, and
                    confidence-aware label chips.
                  </p>
                </div>

                <div style={styles.tracks}>
                  {["QB", "X", "H", "Y", "Z", "RB"].map((track) => (
                    <button key={track} type="button" style={styles.playerDot}>
                      {track}
                    </button>
                  ))}
                </div>
              </div>

              <div style={styles.card}>
                <div>
                  <strong>Editable clip boundaries</strong>
                  <p style={{ margin: "6px 0 0", color: "#546273" }}>
                    Drag start and end handles to match the snap-to-whistle window.
                  </p>
                </div>
                <label>
                  Start: {clipStart.toFixed(1)}s
                  <input
                    type="range"
                    min={0}
                    max={24}
                    step={0.5}
                    value={clipStart}
                    onChange={(event) =>
                      setClipStart(Math.min(Number(event.target.value), clipEnd - 0.5))
                    }
                    style={{ width: "100%" }}
                  />
                </label>
                <label>
                  End: {clipEnd.toFixed(1)}s
                  <input
                    type="range"
                    min={0.5}
                    max={24}
                    step={0.5}
                    value={clipEnd}
                    onChange={(event) =>
                      setClipEnd(Math.max(Number(event.target.value), clipStart + 0.5))
                    }
                    style={{ width: "100%" }}
                  />
                </label>
              </div>
            </div>

            <div style={{ display: "grid", gap: "16px" }}>
              <div style={styles.card}>
                <strong>Label stack</strong>
                {clipLabels.map((item) => (
                  <div
                    key={item.label}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: "12px",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700 }}>{item.label}</div>
                      <div style={{ color: "#546273" }}>{item.value}</div>
                    </div>
                    <span style={badgeStyle("#eaf0f5", toneColor(item.confidence))}>
                      {(item.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
                <div style={styles.buttonRow}>
                  <button type="button" style={styles.button}>
                    Log label correction
                  </button>
                  <button type="button" style={styles.secondaryButton}>
                    Log metric correction
                  </button>
                </div>
              </div>

              <div style={styles.card}>
                <strong>Player identity correction</strong>
                <label style={{ display: "grid", gap: "8px" }}>
                  Clicked player assignment
                  <select
                    value={selectedPlayer}
                    onChange={(event) => setSelectedPlayer(event.target.value)}
                    style={{
                      borderRadius: "10px",
                      border: "1px solid #c4cfda",
                      padding: "10px 12px",
                      background: "#ffffff",
                    }}
                  >
                    {rosterAssignments.map((assignment) => (
                      <option key={assignment.track} value={assignment.suggested}>
                        {assignment.track}: {assignment.suggested}
                      </option>
                    ))}
                  </select>
                </label>

                {rosterAssignments.map((assignment) => (
                  <div key={assignment.track} style={styles.metricCard}>
                    <div style={{ fontWeight: 700 }}>{assignment.track}</div>
                    <div style={{ color: "#546273" }}>Current: {assignment.current}</div>
                    <div style={{ color: "#0d4b82" }}>Suggested: {assignment.suggested}</div>
                  </div>
                ))}

                <div style={styles.buttonRow}>
                  <button type="button" style={styles.button}>
                    Assign {selectedPlayer}
                  </button>
                  <button type="button" style={styles.secondaryButton}>
                    Save correction log
                  </button>
                </div>
              </div>

              {/* Head-orientation metrics in clip review — staff only, never shown to players */}
              {!isPlayerRole && (
                <div style={{ ...styles.card, border: "1px solid #c4b5fd" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <strong>Head orientation (QB) — Clip 144</strong>
                    <span style={badgeStyle("#f3e8ff", "#6b21a8")}>⚗ Experimental</span>
                  </div>
                  <p style={{ margin: 0, color: "#546273", fontSize: "0.9rem" }}>
                    Head-orientation estimation from pose keypoints.
                    Not true eye tracking. Requires position-coach approval before use.
                  </p>
                  {qbProgressionData.map((frame) => (
                    <div key={frame.phase} style={styles.metricCard}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                        <div>
                          <div style={{ fontWeight: 700 }}>{frame.phase}</div>
                          <div style={{ color: "#546273" }}>{frame.targetDescription}</div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontWeight: 700 }}>{frame.yawDegrees}°</div>
                          <span style={badgeStyle("#eaf0f5", toneColor(frame.confidence))}>
                            {(frame.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                  <p style={{ margin: 0, color: "#6b21a8", fontSize: "0.85rem", fontWeight: 600 }}>
                    ⚠ Stare-down detected at release — no head movement snap→throw
                  </p>
                </div>
              )}
            </div>
          </div>
        </section>

        <section id="coach-dashboards" style={styles.section}>
          <div style={styles.sectionHeader}>
            <div>
              <h2 style={{ margin: 0 }}>3. Coach Dashboards</h2>
              <p style={{ margin: "6px 0 0", color: "#546273" }}>
                Formation, motion, effort, and tempo surfaces where every metric is
                evidence-linked within two clicks.
              </p>
            </div>
            <a href="#clip-review" style={{ ...styles.navLink, background: "#102033" }}>
              Jump to evidence clip
            </a>
          </div>

          <div style={styles.grid}>
            <div style={styles.card}>
              <strong>Formation + motion tendency</strong>
              {tendencyData.map((item) => (
                <div key={item.label} style={{ display: "grid", gap: "8px" }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: "12px",
                    }}
                  >
                    <span>{item.label}</span>
                    <a href="#clip-review" style={{ color: "#0d4b82", fontWeight: 700 }}>
                      Evidence: {item.clip}
                    </a>
                  </div>
                  <div style={styles.progressTrack}>
                    <div
                      style={{
                        width: `${item.value}%`,
                        height: "100%",
                        background: "#0d4b82",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            <div style={styles.card}>
              <strong>Effort metrics</strong>
              {effortMetrics.map((item) => (
                <div key={item.metric} style={styles.metricCard}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span>{item.metric}</span>
                    <strong>{item.value}</strong>
                  </div>
                  <a href="#clip-review" style={{ color: "#0d4b82", fontWeight: 700 }}>
                    Open {item.evidence}
                  </a>
                </div>
              ))}
            </div>

            <div style={styles.card}>
              <strong>Practice tempo</strong>
              {practiceTempo.map((item) => (
                <div key={item.metric} style={styles.metricCard}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span>{item.metric}</span>
                    <strong>{item.value}</strong>
                  </div>
                  <a href="#clip-review" style={{ color: "#0d4b82", fontWeight: 700 }}>
                    Open {item.evidence}
                  </a>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="labeling-queue" style={styles.section}>
          <div style={styles.sectionHeader}>
            <div>
              <h2 style={{ margin: 0 }}>4. Labeling Queue</h2>
              <p style={{ margin: "6px 0 0", color: "#546273" }}>
                Review low-confidence plays, roster conflicts, boundary errors,
                regressions, and correction hot spots.
              </p>
            </div>
            <button type="button" style={styles.button}>
              Prioritize review queue
            </button>
          </div>

          <div style={styles.grid}>
            <div style={styles.card}>
              <strong>Queue items</strong>
              {labelingQueue.map((item) => (
                <div key={item.play} style={styles.metricCard}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <div>
                      <div style={{ fontWeight: 700 }}>{item.play}</div>
                      <div>{item.issue}</div>
                      <div style={{ color: "#546273" }}>{item.detail}</div>
                    </div>
                    <span style={priorityBadge(item.priority)}>{item.priority}</span>
                  </div>
                  <div style={styles.buttonRow}>
                    <a href="#clip-review" style={{ color: "#0d4b82", fontWeight: 700 }}>
                      Review clip
                    </a>
                    <button type="button" style={styles.secondaryButton}>
                      Send to analyst
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div style={styles.card}>
              <strong>Correction analytics</strong>
              {correctionAnalytics.map((item) => (
                <div key={item.label} style={styles.metricCard}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span>{item.label}</span>
                    <strong>{item.corrections} corrections</strong>
                  </div>
                  <div style={{ color: "#546273" }}>{item.note}</div>
                </div>
              ))}
            </div>
          </div>

          <p style={styles.footerNote}>
            Evidence links route every chart or queue item back to the clip review
            surface in one tap, keeping the validation workflow within two clicks.
          </p>
        </section>

        {/* ── Head Orientation & Gaze Estimation (staff only) ─────────────── */}
        {!isPlayerRole && (
          <section id="head-orientation" style={styles.section}>
            <div style={styles.sectionHeader}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <h2 style={{ margin: 0 }}>5. Head Orientation &amp; Gaze Estimation</h2>
                  <span style={badgeStyle("#f3e8ff", "#6b21a8")}>⚗ Experimental</span>
                </div>
                <p style={{ margin: "6px 0 0", color: "#546273", maxWidth: "800px" }}>
                  Head-direction vectors derived from pose keypoints (RTMPose / ViTPose).
                  <strong> This is head-orientation estimation — not true eye tracking.</strong>{" "}
                  All metrics require position-coach approval before use. Confidence
                  warnings are always visible. No data is shown in player-facing views.
                </p>
              </div>
              <span style={badgeStyle("#fef3c7", "#92400e")}>
                Pending coach approval
              </span>
            </div>

            {/* Position-coach review workflow */}
            <div style={styles.card}>
              <strong>Position-coach review — approve before staff use</strong>
              <p style={{ margin: 0, color: "#546273", fontSize: "0.9rem" }}>
                The relevant position coach (QB coach or DC) must review and approve
                head-orientation metrics for their group before they appear in any
                staff-facing view. Rejected or flagged metrics are routed to the model
                team and remain hidden.
              </p>
              <div style={styles.buttonRow}>
                {(["approve", "reject", "flag"] as ReviewAction[]).map((action) => (
                  <button
                    key={action}
                    type="button"
                    onClick={() => setHeadOrientationReview(action)}
                    style={
                      headOrientationReview === action
                        ? {
                            ...styles.button,
                            background:
                              action === "approve"
                                ? "#166534"
                                : action === "reject"
                                  ? "#b42318"
                                  : "#92400e",
                          }
                        : styles.secondaryButton
                    }
                  >
                    {action === "approve" ? "✓ Approve" : action === "reject" ? "✗ Reject" : "⚑ Flag for model review"}
                  </button>
                ))}
              </div>
              {headOrientationReview && (
                <div
                  style={{
                    padding: "12px",
                    borderRadius: "10px",
                    background:
                      headOrientationReview === "approve"
                        ? "#d9fbe8"
                        : headOrientationReview === "reject"
                          ? "#fee2e2"
                          : "#fef3c7",
                    color:
                      headOrientationReview === "approve"
                        ? "#166534"
                        : headOrientationReview === "reject"
                          ? "#b42318"
                          : "#92400e",
                    fontWeight: 700,
                  }}
                >
                  {headOrientationReview === "approve" &&
                    "Approved — metrics will be visible to staff in this position group."}
                  {headOrientationReview === "reject" &&
                    "Rejected — metrics remain hidden. Model team notified."}
                  {headOrientationReview === "flag" &&
                    "Flagged — routed to model review queue. Metrics remain hidden."}
                </div>
              )}
            </div>

            <div style={styles.grid}>
              {/* QB Progression Reads */}
              <div style={styles.card}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <strong>QB — Progression reads (Clip 144)</strong>
                  <span style={badgeStyle("#f3e8ff", "#6b21a8")}>⚗</span>
                </div>
                <p style={{ margin: 0, color: "#546273", fontSize: "0.9rem" }}>
                  Head-direction yaw at each dropback phase. Stare-down detected.
                </p>
                {qbProgressionData.map((frame) => (
                  <div key={frame.phase} style={styles.metricCard}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center" }}>
                      <div>
                        <div style={{ fontWeight: 700 }}>{frame.phase}</div>
                        <div style={{ color: "#546273", fontSize: "0.9rem" }}>
                          {frame.targetDescription}
                        </div>
                      </div>
                      <div style={{ textAlign: "right", flexShrink: 0 }}>
                        <div style={{ fontWeight: 700 }}>{frame.yawDegrees > 0 ? "+" : ""}{frame.yawDegrees}°</div>
                        <span style={badgeStyle("#eaf0f5", toneColor(frame.confidence))}>
                          {(frame.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    <a href="#clip-review" style={{ color: "#0d4b82", fontWeight: 700, fontSize: "0.9rem" }}>
                      Open {frame.clip}
                    </a>
                  </div>
                ))}
                <p style={{ margin: 0, color: "#b42318", fontWeight: 600, fontSize: "0.9rem" }}>
                  ⚠ Stare-down detected: no head movement snap→throw. Check primary read fixation.
                </p>
              </div>

              {/* LB / Safety Play-Action Response */}
              <div style={styles.card}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <strong>LB / Safety — Play-action response</strong>
                  <span style={badgeStyle("#f3e8ff", "#6b21a8")}>⚗</span>
                </div>
                <p style={{ margin: 0, color: "#546273", fontSize: "0.9rem" }}>
                  Head-turn latency after play fake. Time from mesh point to correct
                  run/pass read.
                </p>
                {playActionData.map((item) => (
                  <div key={item.position} style={styles.metricCard}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "flex-start" }}>
                      <div>
                        <div style={{ fontWeight: 700 }}>{item.position}</div>
                        <div style={{ color: "#546273", fontSize: "0.9rem" }}>{item.note}</div>
                      </div>
                      <div style={{ textAlign: "right", flexShrink: 0 }}>
                        <div style={{ fontWeight: 700 }}>{item.latencySeconds.toFixed(2)}s</div>
                        <span
                          style={badgeStyle(
                            item.firstStepCorrect ? "#d9fbe8" : "#fee2e2",
                            item.firstStepCorrect ? "#166534" : "#b42318",
                          )}
                        >
                          {item.firstStepCorrect ? "Correct" : "Wrong step"}
                        </span>
                      </div>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={badgeStyle("#eaf0f5", toneColor(item.confidence))}>
                        Conf {(item.confidence * 100).toFixed(0)}%
                      </span>
                      <a href="#clip-review" style={{ color: "#0d4b82", fontWeight: 700, fontSize: "0.9rem" }}>
                        Open {item.clip}
                      </a>
                    </div>
                  </div>
                ))}
              </div>

              {/* CB Technique */}
              <div style={styles.card}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <strong>CB — Technique by coverage</strong>
                  <span style={badgeStyle("#f3e8ff", "#6b21a8")}>⚗</span>
                </div>
                <p style={{ margin: 0, color: "#546273", fontSize: "0.9rem" }}>
                  Head tracking receiver vs. QB by coverage type. Zone: should scan QB
                  + routes. Man: should track receiver.
                </p>
                {cbTechniqueData.map((item, idx) => (
                  <div key={idx} style={styles.metricCard}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "flex-start" }}>
                      <div>
                        <div style={{ fontWeight: 700 }}>
                          {item.player} — {item.coverage}
                        </div>
                        <div style={{ color: "#546273", fontSize: "0.9rem" }}>{item.note}</div>
                      </div>
                      <span
                        style={badgeStyle(
                          item.correct ? "#d9fbe8" : "#fee2e2",
                          item.correct ? "#166534" : "#b42318",
                        )}
                      >
                        {item.correct ? "✓ Correct" : "✗ Incorrect"}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={badgeStyle("#eaf0f5", toneColor(item.confidence))}>
                        Conf {(item.confidence * 100).toFixed(0)}%
                      </span>
                      <a href="#clip-review" style={{ color: "#0d4b82", fontWeight: 700, fontSize: "0.9rem" }}>
                        Open {item.clip}
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <p style={styles.footerNote}>
              Head-orientation estimation uses nose, ear, and eye keypoints from RTMPose /
              ViTPose. Confidence is derived from keypoint visibility and head-occlusion
              heuristics. Metrics with confidence below 0.70 are suppressed.
              All head-orientation data is hidden from player-facing views.
            </p>
          </section>
        )}
      </div>
    </main>
  );
}
