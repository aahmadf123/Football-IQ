"use client";

import { FootballShell } from "@/components/football-shell";
import { LibraryView } from "./library-view";

// Compatibility route (ADR 0003): Library content now lives in Film Room →
// Browse Film. This page is retained so existing deep links keep working and
// renders the same view component the Film Room hub uses.
export default function LibraryPage() {
  return (
    <FootballShell activePage="library">
      <LibraryView />
    </FootballShell>
  );
}
