/**
 * Coach-facing labels for backend enums (single source of truth — previously
 * duplicated across library and clip-review).
 */

import type { OurPossession, SessionKind } from "./types";

export const POSSESSION_LABEL: Record<OurPossession, string> = {
  offense: "Toledo Offense",
  defense: "Toledo Defense",
  special_teams: "Special Teams",
};

export const SESSION_KIND_LABEL: Record<SessionKind, string> = {
  practice: "Practice",
  scrimmage: "Scrimmage",
  game: "Game",
};
