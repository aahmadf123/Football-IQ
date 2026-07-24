"use client";

/**
 * Canonical player profile route for the static export: /players/detail/?id=…
 *
 * A query-param CSR page works for ANY real player id from a cold static
 * load — unlike the old /players/[id] dynamic segment, whose
 * generateStaticParams could only enumerate ids known at build time.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { FootballShell } from "@/components/football-shell";
import { PlayerProfileClient } from "./player-profile-client";

export default function PlayerDetailPage() {
  return (
    <Suspense
      fallback={
        <div style={{ padding: 24 }}>
          <p className="kicker">Loading player profile…</p>
        </div>
      }
    >
      <PlayerDetailContent />
    </Suspense>
  );
}

function PlayerDetailContent() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id") ?? "";
  if (!id) {
    return (
      <FootballShell activePage="players">
        <section className="panel panel-pad">
          <h2 className="panel-title">No player selected</h2>
          <p className="kicker" style={{ marginTop: 8 }}>
            Open a player from the{" "}
            <Link href="/players" style={{ color: "var(--gold)" }}>roster</Link>.
          </p>
        </section>
      </FootballShell>
    );
  }
  return <PlayerProfileClient id={id} />;
}
