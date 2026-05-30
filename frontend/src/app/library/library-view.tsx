"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppState } from "@/lib/app-state";
import {
  fetchClipsForVideo,
  fetchPracticeSessions,
  fetchVideos,
  type PracticeSessionFilters,
  type VideoFilters,
} from "@/lib/api";
import type {
  ApiClip,
  ApiPracticeSessionGroup,
  ApiVideo,
  OurPossession,
  SessionKind,
} from "@/lib/types";

type LibraryState =
  | { kind: "loading" }
  | { kind: "offline" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; sessions: ApiPracticeSessionGroup[]; videos: ApiVideo[] };

const POSSESSION_LABEL: Record<OurPossession, string> = {
  offense: "Toledo Offense",
  defense: "Toledo Defense",
  special_teams: "Special Teams",
};

const SESSION_KIND_LABEL: Record<SessionKind, string> = {
  practice: "Practice",
  scrimmage: "Scrimmage",
  game: "Game",
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "Unknown date";
  try {
    return new Date(value).toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return value;
  }
}

function sessionKey(s: ApiPracticeSessionGroup): string {
  return [
    s.practice_session_id ?? "",
    s.session_date ?? "",
    s.session_kind ?? "",
    s.opponent_team ?? "",
  ].join("|");
}

export function LibraryView() {
  const { selectedDate, sessionType, mockMode, authToken } = useAppState();
  const [opponent, setOpponent] = useState<string>("");
  const [possession, setPossession] = useState<"" | OurPossession>("");
  const [state, setState] = useState<LibraryState>({ kind: "loading" });

  const load = useCallback(async () => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setState({ kind: "offline" });
      return;
    }

    const sessionFilters: PracticeSessionFilters = {};
    const videoFilters: VideoFilters = { limit: 200 };
    if (selectedDate) {
      sessionFilters.recorded_after = `${selectedDate}T00:00:00Z`;
      sessionFilters.recorded_before = `${selectedDate}T23:59:59.999999Z`;
      videoFilters.recorded_after = sessionFilters.recorded_after;
      videoFilters.recorded_before = sessionFilters.recorded_before;
    }
    if (sessionType !== "all") {
      sessionFilters.session_kind = sessionType;
      videoFilters.session_kind = sessionType;
    }
    if (opponent) {
      sessionFilters.opponent_team = opponent;
      videoFilters.opponent_team = opponent;
    }

    setState({ kind: "loading" });
    try {
      const [sessions, videos] = await Promise.all([
        fetchPracticeSessions(sessionFilters, authToken),
        fetchVideos(videoFilters, authToken),
      ]);
      if (sessions.length === 0 && videos.length === 0) {
        setState({ kind: "empty" });
      } else {
        setState({ kind: "ready", sessions, videos });
      }
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, [selectedDate, sessionType, opponent, authToken]);

  useEffect(() => {
    load();
  }, [load]);

  // Group videos under their session group, filtering by possession on the
  // client (possession is a per-video field, not a session-level field).
  const grouped = useMemo(() => {
    if (state.kind !== "ready") return null;
    const videosForGroup = (group: ApiPracticeSessionGroup): ApiVideo[] => {
      const dateStr = group.session_date;
      return state.videos.filter((v) => {
        if (group.practice_session_id) {
          if (v.practice_session_id !== group.practice_session_id) return false;
        } else {
          const vDate = v.recorded_at ? v.recorded_at.slice(0, 10) : null;
          if (vDate !== dateStr) return false;
          if (group.session_kind && v.session_kind !== group.session_kind) return false;
          if (group.opponent_team && v.opponent_team !== group.opponent_team) return false;
        }
        if (possession) {
          // Strict filter: when a possession is selected, exclude videos
          // whose possession is unknown or does not match the selection.
          if (v.our_possession !== possession) return false;
        }
        return true;
      });
    };
    const enriched = state.sessions
      .map((s) => ({ session: s, videos: videosForGroup(s) }))
      .filter((g) => g.videos.length > 0 || !possession);
    const practice = enriched.filter(
      (g) => (g.session.session_kind ?? "practice") !== "game",
    );
    const games = enriched.filter((g) => g.session.session_kind === "game");
    return { practice, games };
  }, [state, possession]);

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-12">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div>
            <h2 className="panel-title">Hudl-style Library</h2>
            <p className="kicker">
              Practice and game film grouped by date and session. Use the top
              filters for date and session kind; opponent and possession refine
              below.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <label className="form-control" style={{ minWidth: 160 }}>
              <span className="small-label">Opponent</span>
              <input
                value={opponent}
                onChange={(e) => setOpponent(e.target.value)}
                placeholder="e.g. Northern Illinois"
                aria-label="Filter by opponent team"
              />
            </label>
            <label className="form-control" style={{ minWidth: 160 }}>
              <span className="small-label">Possession</span>
              <select
                value={possession}
                onChange={(e) => setPossession(e.target.value as "" | OurPossession)}
                aria-label="Filter by possession"
              >
                <option value="">All possessions</option>
                <option value="offense">Toledo Offense</option>
                <option value="defense">Toledo Defense</option>
                <option value="special_teams">Special Teams</option>
              </select>
            </label>
          </div>
        </div>
      </section>

      {state.kind === "loading" && (
        <section className="panel panel-pad span-12">
          <p className="kicker">Loading library…</p>
        </section>
      )}
      {state.kind === "offline" && (
        <section className="panel panel-pad span-12">
          <h3 className="panel-title">Library unavailable</h3>
          <p className="kicker" style={{ marginTop: 8 }}>
            <code>NEXT_PUBLIC_API_URL</code> is not configured. The Library
            requires a backend connection.{mockMode ? " Mock mode is active — server-backed library is hidden in the default UI." : ""}
          </p>
        </section>
      )}
      {state.kind === "error" && (
        <section className="panel panel-pad span-12">
          <h3 className="panel-title">Could not load library</h3>
          <p className="kicker" style={{ marginTop: 8, color: "var(--accent-red, #f87171)" }}>
            {state.message}
          </p>
          <button className="control-button" onClick={load} style={{ marginTop: 12 }}>
            Retry
          </button>
        </section>
      )}
      {state.kind === "empty" && (
        <section className="panel panel-pad span-12">
          <h3 className="panel-title">No film yet</h3>
          <p className="kicker" style={{ marginTop: 8 }}>
            Upload practice or game film from the Film Room → Upload / Process
            Film tab or your Drone integration. Sessions appear here once at
            least one video lands in R2.
          </p>
        </section>
      )}
      {state.kind === "ready" && grouped && (
        <>
          <LibrarySection
            title="Practice & Scrimmage Sessions"
            kind="practice"
            groups={grouped.practice}
          />
          <LibrarySection title="Game Film" kind="game" groups={grouped.games} />
        </>
      )}
    </div>
  );
}

function LibrarySection({
  title,
  kind,
  groups,
}: {
  title: string;
  kind: "practice" | "game";
  groups: Array<{ session: ApiPracticeSessionGroup; videos: ApiVideo[] }>;
}) {
  return (
    <section className="panel panel-pad span-12">
      <h2 className="panel-title">{title}</h2>
      {groups.length === 0 ? (
        <p className="kicker" style={{ marginTop: 8 }}>
          {kind === "game"
            ? "No game film matches the current filters."
            : "No practice or scrimmage sessions match the current filters."}
        </p>
      ) : (
        <div className="list-stack" style={{ marginTop: 12, gap: 12 }}>
          {groups.map((g) => (
            <SessionCard
              key={sessionKey(g.session)}
              session={g.session}
              videos={g.videos}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function SessionCard({
  session,
  videos,
}: {
  session: ApiPracticeSessionGroup;
  videos: ApiVideo[];
}) {
  const [open, setOpen] = useState(false);
  const kindLabel = session.session_kind ? SESSION_KIND_LABEL[session.session_kind] : "Session";
  const opponentLabel = session.session_kind === "game" && session.opponent_team
    ? `vs. ${session.opponent_team}`
    : null;

  return (
    <div
      style={{
        border: "1px solid var(--line-soft, #333)",
        borderRadius: 8,
        background: "var(--surface, transparent)",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`${open ? "Collapse" : "Expand"} session ${formatDate(session.session_date)}`}
        style={{
          width: "100%",
          padding: 12,
          background: "transparent",
          border: "none",
          color: "inherit",
          textAlign: "left",
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div>
          <strong style={{ fontSize: "1rem" }}>
            {formatDate(session.session_date)}
          </strong>
          <div className="kicker" style={{ marginTop: 4 }}>
            {kindLabel}
            {opponentLabel ? ` · ${opponentLabel}` : ""}
            {" · "}
            {session.video_count} video{session.video_count === 1 ? "" : "s"}
          </div>
        </div>
        <span className="status-pill info">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div style={{ padding: "0 12px 12px" }}>
          {videos.length === 0 ? (
            <p className="kicker">No videos match the current possession filter.</p>
          ) : (
            <div className="list-stack" style={{ gap: 8 }}>
              {videos.map((v) => (
                <VideoRow key={v.id} video={v} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function VideoRow({ video }: { video: ApiVideo }) {
  const { authToken } = useAppState();
  const [expanded, setExpanded] = useState(false);
  const [clips, setClips] = useState<ApiClip[] | null>(null);
  const [clipsError, setClipsError] = useState<string | null>(null);
  const [loadingClips, setLoadingClips] = useState(false);

  useEffect(() => {
    if (!expanded || clips !== null) return;
    let cancelled = false;
    setLoadingClips(true);
    setClipsError(null);
    fetchClipsForVideo(video.id, authToken)
      .then((data) => {
        if (!cancelled) setClips(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setClipsError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingClips(false);
      });
    return () => {
      cancelled = true;
    };
  }, [expanded, clips, video.id, authToken]);

  const statusColor = video.status === "ready"
    ? "var(--accent-green, #4ade80)"
    : video.status === "failed"
      ? "var(--accent-red, #f87171)"
      : "var(--accent-amber, #fbbf24)";

  return (
    <div
      style={{
        border: "1px solid var(--line-soft, #333)",
        borderRadius: 6,
        padding: 10,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <strong>{video.filename}</strong>
          <div className="kicker" style={{ marginTop: 4 }}>
            {video.session_kind ? SESSION_KIND_LABEL[video.session_kind] : "Session"}
            {video.opponent_team ? ` · vs. ${video.opponent_team}` : ""}
            {video.our_possession ? ` · ${POSSESSION_LABEL[video.our_possession]}` : ""}
          </div>
        </div>
        <span
          style={{
            color: statusColor,
            fontWeight: 700,
            fontSize: "0.75rem",
            textTransform: "capitalize",
          }}
        >
          {video.status}
        </span>
        <button className="control-button" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Hide clips" : "Show clips"}
        </button>
      </div>
      {expanded && (
        <div style={{ marginTop: 10 }}>
          {loadingClips && <p className="kicker">Loading clips…</p>}
          {clipsError && (
            <p className="kicker" style={{ color: "var(--accent-red, #f87171)" }}>
              {clipsError}
            </p>
          )}
          {clips && clips.length === 0 && (
            <p className="kicker">No clips processed for this video yet.</p>
          )}
          {clips && clips.length > 0 && (
            <div className="list-stack" style={{ marginTop: 6, gap: 4 }}>
              {clips.map((c) => (
                <ClipRow key={c.id} clip={c} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ClipRow({ clip }: { clip: ApiClip }) {
  const possession = clip.our_possession ?? clip.side_of_ball ?? null;
  const possessionLabel = possession ? POSSESSION_LABEL[possession] : null;
  return (
    <Link
      href={`/clip-review/?clipId=${encodeURIComponent(clip.id)}`}
      className="row-button"
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 8,
        textDecoration: "none",
        color: "inherit",
        padding: "6px 8px",
        border: "1px solid var(--line-soft, #333)",
        borderRadius: 6,
      }}
    >
      <div>
        <strong>
          {clip.play_number != null ? `Play #${clip.play_number}` : `Clip ${clip.id.slice(0, 8)}`}
        </strong>
        <div className="kicker" style={{ marginTop: 2 }}>
          {(clip.end_time - clip.start_time).toFixed(1)}s
          {possessionLabel ? ` · ${possessionLabel}` : ""}
          {clip.session_kind ? ` · ${SESSION_KIND_LABEL[clip.session_kind]}` : ""}
        </div>
      </div>
      <span className="status-pill info">Review →</span>
    </Link>
  );
}
