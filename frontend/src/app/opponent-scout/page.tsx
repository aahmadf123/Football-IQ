"use client";

import { FootballShell } from "@/components/football-shell";
import { OpponentScoutView } from "./opponent-scout-view";

// Compatibility route (ADR 0003): Opponent Scout now lives in the Scouting
// workspace → Opponent Prep. Retained so existing deep links keep working and
// renders the same view component the Scouting hub uses.
export default function OpponentScoutPage() {
  return (
    <FootballShell activePage="opponent-scout">
      <OpponentScoutView />
    </FootballShell>
  );
}
