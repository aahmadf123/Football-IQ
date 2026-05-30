"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { FootballShell } from "@/components/football-shell";
import { SelfScoutView } from "@/app/self-scout/self-scout-view";
import { OpponentScoutView } from "@/app/opponent-scout/opponent-scout-view";
import { CollegeDataView } from "@/app/college-data/college-data-view";

const TABS = [
  { key: "tendencies", label: "Our Tendencies" },
  { key: "opponent", label: "Opponent Prep" },
  { key: "college", label: "College Data" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function isTabKey(value: string | null): value is TabKey {
  return TABS.some((t) => t.key === value);
}

export default function ScoutingPage() {
  return (
    <FootballShell activePage="scouting">
      <Suspense
        fallback={
          <section className="panel panel-pad">
            <p className="kicker">Loading Scouting…</p>
          </section>
        }
      >
        <ScoutingContent />
      </Suspense>
    </FootballShell>
  );
}

function ScoutingContent() {
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab: TabKey = isTabKey(tabParam) ? tabParam : "tendencies";

  return (
    <>
      <nav className="tabs" aria-label="Scouting sections" style={{ marginBottom: 12 }}>
        {TABS.map((tab) => (
          <Link
            key={tab.key}
            href={`/scouting/?tab=${tab.key}`}
            className={`tab-button ${tab.key === activeTab ? "active" : ""}`}
            aria-current={tab.key === activeTab ? "page" : undefined}
            data-testid={`scouting-tab-${tab.key}`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      {activeTab === "tendencies" && <SelfScoutView />}
      {activeTab === "opponent" && <OpponentScoutView />}
      {activeTab === "college" && <CollegeDataView />}
    </>
  );
}
