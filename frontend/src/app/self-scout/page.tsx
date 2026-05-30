"use client";

import { FootballShell } from "@/components/football-shell";
import { SelfScoutView } from "./self-scout-view";

// Compatibility route (ADR 0003): Self-Scout now lives in the Scouting
// workspace → Our Tendencies. Retained so existing deep links keep working and
// renders the same view component the Scouting hub uses.
export default function SelfScoutPage() {
  return (
    <FootballShell activePage="self-scout">
      <SelfScoutView />
    </FootballShell>
  );
}
