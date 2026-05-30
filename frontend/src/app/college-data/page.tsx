"use client";

import { FootballShell } from "@/components/football-shell";
import { CollegeDataView } from "./college-data-view";

// Compatibility route (ADR 0003): College Data (CFBD) now lives in the Scouting
// workspace → College Data. Retained so existing deep links keep working and
// renders the same view component the Scouting hub uses.
export default function CollegeDataPage() {
  return (
    <FootballShell activePage="college-data">
      <CollegeDataView />
    </FootballShell>
  );
}
