"use client";

/**
 * Players roster view (extracted from the old page-renderer monolith).
 *
 * Lists the live roster (identity from /api/v1/players via app-state) with a
 * client-side search, plus a focus panel for the hovered/selected player.
 * Performance metrics that are not wired to the live pipeline yet render "—"
 * instead of fabricated numbers (#103).
 */

import Link from "next/link";
import { Search, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { useAppState, type ApiStatus } from "@/lib/app-state";
import { Metric } from "@/components/shared/metric";
import { PlayerPortrait } from "@/components/shared/player-portrait";
import type { PlayerSummary } from "@/lib/types";

/** Canonical profile link — CSR detail page that works for any real id. */
export function playerProfileHref(id: string): string {
  return `/players/detail/?id=${encodeURIComponent(id)}`;
}

export function PlayersView() {
  const { data, filteredPlayers, selectedPlayer, setSelectedPlayerId, playersStatus } = useAppState();
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const list = filteredPlayers.length ? filteredPlayers : data.players;
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.position.toLowerCase().includes(q) ||
        p.jersey.includes(q),
    );
  }, [filteredPlayers, data.players, query]);

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-8">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <h2 className="panel-title">Roster Intelligence</h2>
          <label className="search-inline">
            <Search size={15} />
            <input
              placeholder="Search by name, jersey, or position"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {visible.length === 0 && (
            <div className="kicker">
              {query.trim() ? "No players match the current filter." : rosterEmptyMessage(playersStatus)}
            </div>
          )}
          {visible.map((player) => (
            <Link
              key={player.id}
              href={playerProfileHref(player.id)}
              className="table-row table-row-link"
              onMouseEnter={() => setSelectedPlayerId(player.id)}
            >
              <strong>#{player.jersey} {player.name}</strong>
              <span>{player.position}</span>
              <span>{fmtMetric(player.maxSpeed)} MPH</span>
              <span>{fmtMetric(player.distance)} YDS</span>
              <span className="status-pill info">{fmtConfidence(player.confidence)}</span>
            </Link>
          ))}
        </div>
      </section>
      <section className="panel panel-pad span-4">
        {selectedPlayer ? (
          <>
            <PlayerFocus
              player={selectedPlayer}
              allPlayers={visible.length ? visible : data.players}
              onSelect={setSelectedPlayerId}
            />
            <Link href={playerProfileHref(selectedPlayer.id)} className="control-button primary" style={{ marginTop: 12, textDecoration: "none", justifyContent: "center" }}>
              <UserRound size={15} /> Open Full Profile
            </Link>
          </>
        ) : (
          <>
            <h2 className="panel-title">Player Focus</h2>
            <p className="kicker" style={{ marginTop: 8 }}>{rosterEmptyMessage(playersStatus)}</p>
          </>
        )}
      </section>
    </div>
  );
}

/**
 * Focus panel for one player: identity portrait + roster switcher + the
 * pipeline metrics (which render "—" until per-player tracking lands).
 * Shared by the Players and Player Development views.
 */
export function PlayerFocus({
  player,
  allPlayers,
  onSelect,
  compact = false,
}: {
  player: PlayerSummary;
  allPlayers: PlayerSummary[];
  onSelect: (id: string) => void;
  compact?: boolean;
}) {
  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <h2 className="panel-title">Player Focus</h2>
        <select
          className="inline-select"
          value={player.id}
          onChange={(e) => onSelect(e.target.value)}
          aria-label="Choose player"
        >
          {allPlayers.map((p) => (
            <option key={p.id} value={p.id}>#{p.jersey} {p.name}</option>
          ))}
        </select>
      </div>
      <Link href={playerProfileHref(player.id)} style={{ textDecoration: "none", color: "inherit", display: "block", marginTop: 6 }}>
        <PlayerPortrait player={player} compact={compact} />
      </Link>
      <div className="metric-grid" style={{ marginTop: compact ? 8 : 12, gridTemplateColumns: "repeat(3, 1fr)" }}>
        <Metric label="Distance" value={fmtMetric(player.distance)} unit="YDS" />
        <Metric label="Max Speed" value={fmtMetric(player.maxSpeed)} unit="MPH" />
        <Metric label="Avg Sep" value={fmtMetric(player.separation)} unit="YDS" />
      </div>
    </>
  );
}

export function rosterEmptyMessage(status: ApiStatus): string {
  switch (status) {
    case "loading":
      return "Loading roster…";
    case "offline":
      return "Roster unavailable — could not reach /api/v1/players.";
    case "live":
      return "Roster is empty. Add players from Settings to populate this view.";
    case "mock":
      return "No players yet.";
    default:
      return "No players yet.";
  }
}

// Render an optional numeric metric as a string. Metrics that aren't wired to
// the live backend yet (max speed, separation, distance) are surfaced as a
// dash rather than fabricated zeros — see Issue #103 acceptance criteria.
export function fmtMetric(value: number | undefined): string {
  return value == null ? "—" : String(value);
}

export function fmtConfidence(value: number | undefined): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}
