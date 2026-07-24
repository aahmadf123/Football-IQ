"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AnalyticsCard, type AnalyticsCardState } from "@/components/analytics-card";
import { TendencyTable } from "@/components/shared/tendency-table";
import { useAppState } from "@/lib/app-state";
import type { FetchState } from "@/lib/fetch-state";
import {
  fetchOpponentTendencies,
  fetchOpponents,
} from "@/lib/api";
import type {
  OpponentSummary,
  OpponentVideo,
  SelfScoutResponse,
} from "@/lib/types";

type OpponentListState = FetchState<OpponentSummary[]>;

// Adds "idle" (no film selected yet) on top of the shared fetch lifecycle.
type TendencyState = { kind: "idle" } | FetchState<SelfScoutResponse>;

export function OpponentScoutView() {
  const { authToken, mockMode } = useAppState();
  const [opponentList, setOpponentList] = useState<OpponentListState>({
    kind: "loading",
  });
  const [selectedOpponent, setSelectedOpponent] = useState<string>("");
  const [selectedVideo, setSelectedVideo] = useState<string>("");
  const [tendencyState, setTendencyState] = useState<TendencyState>({
    kind: "idle",
  });

  const loadOpponents = useCallback(async () => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setOpponentList({ kind: "offline" });
      return;
    }
    setOpponentList({ kind: "loading" });
    try {
      const opponents = await fetchOpponents(authToken);
      if (opponents.length === 0) {
        setOpponentList({ kind: "empty" });
      } else {
        setOpponentList({ kind: "ready", data: opponents });
      }
    } catch (err) {
      setOpponentList({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, [authToken]);

  useEffect(() => {
    loadOpponents();
  }, [loadOpponents]);

  const currentOpponent = useMemo<OpponentSummary | null>(() => {
    if (opponentList.kind !== "ready") return null;
    if (!selectedOpponent) return null;
    return (
      opponentList.data.find((o) => o.opponent_team === selectedOpponent) ?? null
    );
  }, [opponentList, selectedOpponent]);

  // When the opponent changes, default the video selection to the most recent
  // film for that opponent (the backend returns videos newest-first).
  useEffect(() => {
    if (!currentOpponent) {
      setSelectedVideo("");
      return;
    }
    const first = currentOpponent.videos[0];
    setSelectedVideo(first ? first.video_id : "");
  }, [currentOpponent]);

  const loadTendencies = useCallback(async () => {
    if (!selectedVideo) {
      setTendencyState({ kind: "idle" });
      return;
    }
    setTendencyState({ kind: "loading" });
    try {
      const data = await fetchOpponentTendencies(selectedVideo, authToken);
      if (data.clip_count === 0) {
        setTendencyState({ kind: "empty" });
      } else {
        setTendencyState({ kind: "ready", data });
      }
    } catch (err) {
      setTendencyState({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, [selectedVideo, authToken]);

  useEffect(() => {
    loadTendencies();
  }, [loadTendencies]);

  const cardState = useMemo<AnalyticsCardState>(() => {
    if (opponentList.kind === "offline") {
      return {
        kind: "unavailable",
        reason:
          "Opponent Scout needs the FastAPI backend. Set NEXT_PUBLIC_API_URL to enable.",
      };
    }
    if (opponentList.kind === "error") {
      return {
        kind: "error",
        message: opponentList.message,
        onRetry: loadOpponents,
      };
    }
    if (opponentList.kind === "empty") {
      return {
        kind: "empty",
        reason:
          "No opponent film uploaded yet. Upload a game-tagged video with an opponent team to populate this picker.",
      };
    }
    if (!selectedOpponent) {
      return {
        kind: "empty",
        reason: "Pick an opponent above to load tendencies.",
      };
    }
    if (!selectedVideo) {
      return {
        kind: "empty",
        reason:
          "This opponent has no scoutable film. Upload an opponent cutup tagged to this team.",
      };
    }
    switch (tendencyState.kind) {
      case "idle":
      case "loading":
        return { kind: "loading", label: "Computing opponent tendencies…" };
      case "offline":
        return {
          kind: "unavailable",
          reason:
            "Opponent Scout needs the FastAPI backend. Set NEXT_PUBLIC_API_URL to enable.",
        };
      case "empty":
        return {
          kind: "empty",
          reason:
            "Opponent film is uploaded but no labeled plays are available yet. The labeling pipeline may still be running.",
        };
      case "error":
        return {
          kind: "error",
          message: tendencyState.message,
          onRetry: loadTendencies,
        };
      case "ready":
        return { kind: "live" };
    }
  }, [opponentList, selectedOpponent, selectedVideo, tendencyState, loadOpponents, loadTendencies]);

  const data = tendencyState.kind === "ready" ? tendencyState.data : null;

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
            <h2 className="panel-title">Opponent picker</h2>
            <p className="kicker">
              Game-plan against a specific opponent. Opponents are derived from
              uploaded game film tagged with a team name.
              {mockMode ? " Mock mode shows whatever the backend returns when configured." : ""}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <OpponentPicker
              state={opponentList}
              selected={selectedOpponent}
              onChange={setSelectedOpponent}
            />
            <VideoPicker
              opponent={currentOpponent}
              selected={selectedVideo}
              onChange={setSelectedVideo}
            />
          </div>
        </div>
        {opponentList.kind === "ready" && opponentList.data.length > 0 && (
          <p className="kicker" style={{ marginTop: 8 }}>
            {opponentList.data.length} opponent
            {opponentList.data.length === 1 ? "" : "s"} loaded.
          </p>
        )}
      </section>

      <AnalyticsCard
        title="Run / Pass by Formation"
        state={cardState}
        className="span-6"
      >
        {data && <TendencyTable entries={data.formation_tendencies} />}
      </AnalyticsCard>

      <AnalyticsCard
        title="Personnel Tendencies"
        state={cardState}
        className="span-6"
      >
        {data && <TendencyTable entries={data.personnel_tendencies} />}
      </AnalyticsCard>

      <AnalyticsCard
        title="Pre-Snap Tells"
        state={cardState}
        className="span-12"
      >
        {data &&
          (data.pre_snap_tells.length === 0 ? (
            <p className="kicker">
              No exposure leans crossed the alert threshold for this film.
            </p>
          ) : (
            <div className="list-stack" style={{ gap: 6 }}>
              {data.pre_snap_tells.map((tell) => (
                <div
                  key={tell.grouping_key}
                  className="status-row"
                  style={{ gridTemplateColumns: "1fr auto" }}
                  data-testid={`opp-pre-snap-tell-${tell.grouping_key}`}
                >
                  <div>
                    <strong>{tell.formation}</strong>
                    <div className="kicker">{tell.message}</div>
                  </div>
                  <span
                    className={`status-pill ${tell.severity === "high" ? "danger" : "warning"}`}
                  >
                    {tell.severity}
                  </span>
                </div>
              ))}
            </div>
          ))}
      </AnalyticsCard>
    </div>
  );
}

function OpponentPicker({
  state,
  selected,
  onChange,
}: {
  state: OpponentListState;
  selected: string;
  onChange: (value: string) => void;
}) {
  const disabled = state.kind !== "ready";
  return (
    <label className="form-control" style={{ minWidth: 220 }}>
      <span className="small-label">Opponent</span>
      <select
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-label="Opponent"
        data-testid="opponent-picker"
      >
        <option value="">
          {state.kind === "loading"
            ? "Loading opponents…"
            : state.kind === "empty"
              ? "No opponent film yet"
              : state.kind === "offline"
                ? "Backend offline"
                : state.kind === "error"
                  ? "Could not load opponents"
                  : "Select an opponent"}
        </option>
        {state.kind === "ready" &&
          state.data.map((o) => (
            <option key={o.opponent_team} value={o.opponent_team}>
              {o.opponent_team} ({o.video_count} video{o.video_count === 1 ? "" : "s"})
            </option>
          ))}
      </select>
    </label>
  );
}

function VideoPicker({
  opponent,
  selected,
  onChange,
}: {
  opponent: OpponentSummary | null;
  selected: string;
  onChange: (value: string) => void;
}) {
  const videos = opponent?.videos ?? [];
  return (
    <label className="form-control" style={{ minWidth: 260 }}>
      <span className="small-label">Opponent film</span>
      <select
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        disabled={!opponent || videos.length === 0}
        aria-label="Opponent film"
        data-testid="opponent-video-picker"
      >
        <option value="">
          {!opponent
            ? "Pick an opponent first"
            : videos.length === 0
              ? "No film uploaded"
              : "Select film"}
        </option>
        {videos.map((v) => (
          <option key={v.video_id} value={v.video_id}>
            {opponentVideoLabel(v)}
          </option>
        ))}
      </select>
    </label>
  );
}

function opponentVideoLabel(v: OpponentVideo): string {
  const date = v.recorded_at ? v.recorded_at.slice(0, 10) : v.created_at.slice(0, 10);
  return `${date} · ${v.filename}`;
}
