"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  CalendarDays,
  ChevronDown,
  ClipboardList,
  Clapperboard,
  FileText,
  HeartPulse,
  Home,
  LineChart,
  MonitorPlay,
  Radio,
  Settings,
  ShieldCheck,
  UserRound,
  UsersRound,
  Zap,
} from "lucide-react";
import { footballData, pageTitles } from "@/lib/mock-data";
import type { PageKey } from "@/lib/types";

const navItems = [
  { key: "dashboard", label: "Dashboard", href: "/", icon: Home },
  { key: "video-and-plays", label: "Video & Plays", href: "/video-and-plays", icon: MonitorPlay },
  { key: "players", label: "Players", href: "/players", icon: UserRound },
  { key: "analytics", label: "Analytics", href: "/analytics", icon: LineChart },
  { key: "self-scout", label: "Self-Scout", href: "/self-scout", icon: ShieldCheck },
  { key: "opponent-scout", label: "Opponent Scout", href: "/opponent-scout", icon: ClipboardList },
  { key: "player-development", label: "Player Development", href: "/player-development", icon: UsersRound },
  { key: "health-workload", label: "Health & Workload", href: "/health-workload", icon: HeartPulse },
  { key: "reports", label: "Reports", href: "/reports", icon: FileText },
  { key: "clips-highlights", label: "Clips & Highlights", href: "/clips-highlights", icon: Clapperboard },
  { key: "settings", label: "Settings", href: "/settings", icon: Settings },
] as const;

export function FootballShell({
  activePage,
  children,
}: {
  activePage: PageKey;
  children: React.ReactNode;
}) {
  const pathname = usePathname();

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
          <button type="button" className="select-pill" aria-label="Practice session">
            <CalendarDays size={18} />
            <span>
              Session Type
              <strong>Practice & Games</strong>
            </span>
            <ChevronDown size={16} />
          </button>
          <button type="button" className="select-pill" aria-label="Play filter">
            <BarChart3 size={18} />
            <span>
              Side of Ball
              <strong>All (Off & Def)</strong>
            </span>
            <ChevronDown size={16} />
          </button>
          <div className="user-pill" aria-label="User profile">
            UT
          </div>
        </div>
      </header>

      <aside className="sidebar">
        <nav className="nav-list" aria-label="Football IQ navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || activePage === item.key;
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
            <MetricLine label="Opponent Film" value="Games & Scrim" />
            <MetricLine label="Offense Plays" value="Comp. Tracked" />
            <MetricLine label="Defense Plays" value="Comp. Tracked" />
            <MetricLine label="Practice / Game" value="Full Custom" />
            <MetricLine label="Total Clips" value="Active Roster" />
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
            <h2 style={{ margin: 0, fontSize: activePage === "dashboard" ? "1.0rem" : "1.1rem" }}>{pageTitles[activePage].title}</h2>
            <p className="kicker" style={{ fontSize: activePage === "dashboard" ? "0.72rem" : undefined }}>{pageTitles[activePage].subtitle}</p>
          </div>
          {activePage === "dashboard" && <span className="live-badge" style={{ background: "var(--blue)" }}>Processed</span>}
        </div>
        {children}
      </main>

      <aside className="right-rail">
        <section className="panel panel-pad">
          <h2 className="panel-title" style={{ color: "var(--gold)" }}>System Status</h2>
          <div className="list-stack" style={{ marginTop: 12 }}>
            <StatusLine icon={<Radio size={16} />} label="R2 Buckets" value="Connected" tone="good" />
            <StatusLine icon={<Activity size={16} />} label="Processing" value="Pending upload" tone="good" />
            <StatusLine icon={<UsersRound size={16} />} label="Auto ML IQ" value="Enabled" tone="good" />
            <StatusLine icon={<Zap size={16} />} label="Model Version" value="v2.4.1" tone="good" />
          </div>
        </section>

        <section className="panel panel-pad">
          <h2 className="panel-title" style={{ color: "var(--gold)" }}>Confidence Score</h2>
          <div style={{ display: "grid", placeItems: "center", margin: "18px 0" }}>
            <div className="donut">
              <div>
                <span style={{ display: "block", fontSize: "1.45rem" }}>92%</span>
                <small style={{ color: "var(--muted)" }}>Overall</small>
              </div>
            </div>
          </div>
          <MetricLine label="Video Quality" value="Good" />
          <MetricLine label="Field Calibration" value="95%" />
          <MetricLine label="Tracking Quality" value="High" />
        </section>

        <section className="panel panel-pad">
          <h2 className="panel-title" style={{ color: "var(--gold)" }}>Model Pipeline</h2>
          <div className="list-stack" style={{ marginTop: 12 }}>
            {footballData.jobs.map((job) => (
              <div key={job.id} className={`pipeline-stage ${job.status === "running" ? "running" : ""}`}>
                <i />
                <span>{job.job_type}</span>
              </div>
            ))}
          </div>
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
