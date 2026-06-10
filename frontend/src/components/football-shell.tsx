"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  BellRing,
  CalendarDays,
  ChevronDown,
  ClipboardList,
  Clapperboard,
  FileText,
  HeartPulse,
  Home,
  LineChart,
  Radio,
  Settings,
  UserRound,
  UsersRound,
} from "lucide-react";
import { pageTitles } from "@/lib/mock-data";
import type { PageKey } from "@/lib/types";
import {
  SESSION_LABELS,
  SIDE_LABELS,
  useAppState,
  type ApiStatus,
  type SessionType,
  type SideOfBall,
} from "@/lib/app-state";
import { MockBadge } from "@/components/mock-badge";
import { canAccessHealthWorkload } from "@/lib/roles";

// Consolidated coach-facing navigation (ADR 0003). Film Room and Scouting are
// workspace hubs; Analytics is surfaced as "Model Insights". Alerts moved to a
// top-bar inbox bell, and College Data lives inside the Scouting workspace.
const navItems = [
  { key: "dashboard", label: "Dashboard", href: "/", icon: Home },
  { key: "film-room", label: "Film Room", href: "/film-room", icon: Clapperboard },
  { key: "scouting", label: "Scouting", href: "/scouting", icon: ClipboardList },
  { key: "players", label: "Players", href: "/players", icon: UserRound },
  { key: "player-development", label: "Player Development", href: "/player-development", icon: UsersRound },
  { key: "health-workload", label: "Health & Workload", href: "/health-workload", icon: HeartPulse },
  { key: "analytics", label: "Model Insights", href: "/analytics", icon: LineChart },
  { key: "reports", label: "Reports", href: "/reports", icon: FileText },
  { key: "settings", label: "Settings", href: "/settings", icon: Settings },
] as const;

// Compatibility routes (ADR 0003) that fold into a hub. Used to keep the hub
// nav item highlighted when a coach lands on an old deep link.
const COMPAT_ACTIVE: Partial<Record<PageKey, PageKey>> = {
  library: "film-room",
  "video-and-plays": "film-room",
  "clips-highlights": "film-room",
  "self-scout": "scouting",
  "opponent-scout": "scouting",
  "college-data": "scouting",
};

function formatDateLabel(value: string): string {
  if (!value) return "All dates";
  try {
    const d = new Date(value + "T12:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return value;
  }
}

export function FootballShell({
  activePage,
  children,
}: {
  activePage: PageKey;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const {
    sessionType,
    setSessionType,
    sideOfBall,
    setSideOfBall,
    selectedDate,
    setSelectedDate,
    availableDates,
    data,
    uploads,
    filteredPlays,
    apiStatus,
    currentRole,
  } = useAppState();

  const titleEntry = pageTitles[activePage];
  const navActiveKey = COMPAT_ACTIVE[activePage] ?? activePage;

  // Health & Workload is hidden unless the role is approved (Issue #113). The
  // page itself also gates its content, so a deep link can't bypass this.
  const visibleNavItems = navItems.filter(
    (item) => item.key !== "health-workload" || canAccessHealthWorkload(currentRole),
  );
  const totalPlays = filteredPlays.length;
  const totalClips = data.clips.length + uploads.length;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <Image
            src="/brand/toledo-rocket.png"
            width={184}
            height={52}
            alt="Toledo Football IQ"
            style={{ width: "auto", height: "36px", objectFit: "contain" }}
            priority
          />
        </div>

        <div className="mission">
          <span className="mission-rule" />
          <div>
            <h1>See more. Coach smarter. Win together.</h1>
            <p>Data. Video. Insights. Development.</p>
          </div>
        </div>

        <div className="top-actions">
          <label className="select-pill" aria-label="Select date">
            <CalendarDays size={18} />
            <span>
              Practice Date
              <strong>{formatDateLabel(selectedDate)}</strong>
            </span>
            <ChevronDown size={16} />
            <select
              className="pill-select"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
            >
              {availableDates.map((d) => (
                <option key={d} value={d}>{formatDateLabel(d)}</option>
              ))}
            </select>
          </label>

          <label className="select-pill" aria-label="Session type">
            <CalendarDays size={18} />
            <span>
              Session Type
              <strong>{SESSION_LABELS[sessionType]}</strong>
            </span>
            <ChevronDown size={16} />
            <select
              className="pill-select"
              value={sessionType}
              onChange={(e) => setSessionType(e.target.value as SessionType)}
            >
              {(Object.keys(SESSION_LABELS) as SessionType[]).map((k) => (
                <option key={k} value={k}>{SESSION_LABELS[k]}</option>
              ))}
            </select>
          </label>

          <label className="select-pill" aria-label="Side of ball">
            <BarChart3 size={18} />
            <span>
              Side of Ball
              <strong>{SIDE_LABELS[sideOfBall]}</strong>
            </span>
            <ChevronDown size={16} />
            <select
              className="pill-select"
              value={sideOfBall}
              onChange={(e) => setSideOfBall(e.target.value as SideOfBall)}
            >
              {(Object.keys(SIDE_LABELS) as SideOfBall[]).map((k) => (
                <option key={k} value={k}>{SIDE_LABELS[k]}</option>
              ))}
            </select>
          </label>

          <Link
            href="/alerts"
            className={`alerts-bell ${navActiveKey === "alerts" ? "active" : ""}`}
            aria-label="Coaching alerts inbox"
            title="Coaching alerts inbox"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 40,
              height: 40,
              borderRadius: 10,
              border: "1px solid var(--line-soft)",
              color: "var(--text)",
              flexShrink: 0,
            }}
          >
            <BellRing size={18} />
          </Link>

          <div className="user-pill" aria-label="User profile">UT</div>
        </div>
      </header>

      <aside className="sidebar">
        <nav className="nav-list" aria-label="Football IQ navigation">
          {visibleNavItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              pathname === item.href ||
              (item.href !== "/" && pathname?.startsWith(item.href)) ||
              navActiveKey === item.key;
            return (
              <Link key={item.key} href={item.href} className={`nav-link ${isActive ? "active" : ""}`}>
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <section className="panel panel-pad">
          <h2 className="panel-title">Session Summary</h2>
          <div className="list-stack" style={{ marginTop: 12 }}>
            <MetricLine label="Session" value={SESSION_LABELS[sessionType]} />
            <MetricLine label="Side of Ball" value={SIDE_LABELS[sideOfBall]} />
            <MetricLine label="Date" value={formatDateLabel(selectedDate)} />
            <MetricLine label="Plays" value={String(totalPlays)} />
            <MetricLine label="Clips" value={String(totalClips)} />
          </div>
        </section>

        <section className="panel panel-pad" style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
          <Image src="/brand/toledo-rocket.png" width={140} height={60} alt="" style={{ objectFit: "contain", marginBottom: 8 }} />
          <h2 className="panel-title">Rise Together</h2>
          <p style={{ margin: "6px 0 0", color: "var(--gold)", fontWeight: 900 }}>#TEAMTOLEDO</p>
        </section>
      </aside>

      <main className="main">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: activePage === "dashboard" ? 6 : 12 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: activePage === "dashboard" ? "1.0rem" : "1.1rem" }}>
              {titleEntry.title}
              <MockBadge status={apiStatus} />
            </h2>
            <p className="kicker" style={{ fontSize: activePage === "dashboard" ? "0.72rem" : undefined }}>{titleEntry.subtitle}</p>
          </div>
          {activePage === "dashboard" && apiStatus === "live" && (
            <span className="live-badge" style={{ background: "var(--blue)" }}>Processed</span>
          )}
        </div>
        {children}
      </main>

      <aside className="right-rail">
        <section className="panel panel-pad">
          <h2 className="panel-title" style={{ color: "var(--gold)" }}>System Status</h2>
          <div className="list-stack" style={{ marginTop: 12 }}>
            <StatusLine
              icon={<Radio size={16} />}
              label="API"
              value={apiStatusLabel(apiStatus)}
              tone={apiStatusTone(apiStatus)}
            />
            <StatusLine
              icon={<Activity size={16} />}
              label="Processing"
              value={uploads.length ? `${uploads.length} queued` : "Idle"}
              tone="good"
            />
            <StatusLine
              icon={<UsersRound size={16} />}
              label="Mode"
              value={apiStatusModeLabel(apiStatus)}
              tone={apiStatus === "live" ? "good" : "warning"}
            />
          </div>
        </section>

        <section className="panel panel-pad">
          <h2 className="panel-title" style={{ color: "var(--gold)" }}>Confidence Score</h2>
          {/* Per-clip confidence is wired in #102. Until a clip is selected we
              show an empty state rather than a hardcoded 92%. */}
          <div style={{ display: "grid", placeItems: "center", margin: "18px 0" }}>
            <p style={{ color: "var(--muted)", fontSize: "0.85rem", textAlign: "center", margin: 0 }}>
              No clip selected
            </p>
          </div>
        </section>

        <section className="panel panel-pad">
          <h2 className="panel-title" style={{ color: "var(--gold)" }}>Model Pipeline</h2>
          {data.jobs.length === 0 ? (
            <p style={{ color: "var(--muted)", fontSize: "0.82rem", marginTop: 12 }}>
              No jobs yet.
            </p>
          ) : (
            <div className="list-stack" style={{ marginTop: 12 }}>
              {data.jobs.map((job) => (
                <div key={job.id} className={`pipeline-stage ${job.status === "running" ? "running" : ""}`}>
                  <i />
                  <span>{job.job_type}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, color: "var(--muted)", fontSize: "0.82rem" }}>
      <span>{label}</span>
      <strong style={{ color: "var(--text)" }}>{value}</strong>
    </div>
  );
}

function apiStatusLabel(status: ApiStatus): string {
  switch (status) {
    case "live": return "Connected";
    case "loading": return "Connecting…";
    case "offline": return "Offline";
    case "mock": return "Mock";
    case "idle":
    default: return "—";
  }
}

function apiStatusModeLabel(status: ApiStatus): string {
  switch (status) {
    case "live": return "Live";
    case "loading": return "Live (loading)";
    case "offline": return "Offline";
    case "mock": return "Mock";
    case "idle":
    default: return "—";
  }
}

function apiStatusTone(status: ApiStatus): "good" | "warning" {
  return status === "live" ? "good" : "warning";
}

function StatusLine({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: "good" | "warning";
}) {
  return (
    <div className="status-line">
      <div className="status-line-left">
        {icon}
        <span>{label}</span>
      </div>
      <strong style={{ color: tone === "good" ? "var(--green)" : "var(--gold)", fontSize: "0.80rem" }}>{value}</strong>
    </div>
  );
}
