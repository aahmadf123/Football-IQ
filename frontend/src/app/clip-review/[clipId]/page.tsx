"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { FootballShell } from "@/components/football-shell";
import {
  fetchClip,
  fetchVideo,
  fetchVideoDownloadUrl,
} from "@/lib/api";
import type { ApiClip, ApiVideo, OurPossession, SessionKind } from "@/lib/types";

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

type ReviewState =
  | { kind: "loading" }
  | { kind: "offline" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      clip: ApiClip;
      video: ApiVideo;
      playbackUrl: string | null;
      playbackUnavailable: boolean;
    };

export default function ClipReviewPage({
  params,
}: {
  params: Promise<{ clipId: string }>;
}) {
  const { clipId } = use(params);
  return (
    <FootballShell activePage="clip-review">
      <ClipReviewView clipId={clipId} />
    </FootballShell>
  );
}

function ClipReviewView({ clipId }: { clipId: string }) {
  const [state, setState] = useState<ReviewState>({ kind: "loading" });

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setState({ kind: "offline" });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const clip = await fetchClip(clipId);
        const video = await fetchVideo(clip.video_id);
        let playbackUrl: string | null = null;
        let playbackUnavailable = false;
        try {
          playbackUrl = await fetchVideoDownloadUrl(video.id);
          if (!playbackUrl) playbackUnavailable = true;
        } catch {
          playbackUnavailable = true;
        }
        if (cancelled) return;
        setState({ kind: "ready", clip, video, playbackUrl, playbackUnavailable });
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clipId]);

  if (state.kind === "loading") {
    return (
      <section className="panel panel-pad">
        <p className="kicker">Loading clip metadata…</p>
      </section>
    );
  }
  if (state.kind === "offline") {
    return (
      <section className="panel panel-pad">
        <h3 className="panel-title">Backend not configured</h3>
        <p className="kicker" style={{ marginTop: 8 }}>
          Clip Review requires <code>NEXT_PUBLIC_API_URL</code>.
        </p>
        <Link href="/library" className="control-button" style={{ marginTop: 12 }}>
          ← Back to Library
        </Link>
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section className="panel panel-pad">
        <h3 className="panel-title">Could not load clip</h3>
        <p className="kicker" style={{ marginTop: 8, color: "var(--accent-red, #f87171)" }}>
          {state.message}
        </p>
        <Link href="/library" className="control-button" style={{ marginTop: 12 }}>
          ← Back to Library
        </Link>
      </section>
    );
  }

  const { clip, video, playbackUrl, playbackUnavailable } = state;
  const possession = clip.our_possession ?? clip.side_of_ball ?? video.our_possession ?? null;
  const possessionLabel = possession ? POSSESSION_LABEL[possession] : null;
  const sessionKindLabel = clip.session_kind
    ? SESSION_KIND_LABEL[clip.session_kind]
    : video.session_kind
      ? SESSION_KIND_LABEL[video.session_kind]
      : "Session";

  return (
    <div className="content-grid">
      <section className="panel span-8 panel-pad">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <div>
            <h2 className="panel-title">
              {clip.play_number != null
                ? `Play #${clip.play_number}`
                : `Clip ${clip.id.slice(0, 8)}`}
            </h2>
            <p className="kicker">
              {sessionKindLabel}
              {video.opponent_team ? ` · vs. ${video.opponent_team}` : ""}
              {possessionLabel ? ` · ${possessionLabel}` : ""}
            </p>
          </div>
          <Link href="/library" className="control-button">← Library</Link>
        </div>

        <div
          style={{
            marginTop: 12,
            background: "#000",
            borderRadius: 8,
            minHeight: 320,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {playbackUrl ? (
            <video
              src={playbackUrl}
              controls
              playsInline
              aria-label={`Clip ${clip.play_number ?? clip.id} video`}
              style={{ width: "100%", maxHeight: 480 }}
            />
          ) : (
            <div style={{ color: "var(--muted, #94a3b8)", textAlign: "center", padding: 24 }}>
              <p style={{ margin: 0, fontWeight: 700 }}>Video playback URL not yet available</p>
              <p className="kicker" style={{ marginTop: 8 }}>
                Backend-backed clip metadata loaded; signed playback URLs from
                the Cloudflare Worker are not wired for this clip yet.
                {playbackUnavailable ? " The Worker download endpoint returned no URL." : ""}
              </p>
            </div>
          )}
        </div>

        <p className="kicker" style={{ marginTop: 8 }}>
          {clip.start_time.toFixed(1)}s – {clip.end_time.toFixed(1)}s
          {" "}({(clip.end_time - clip.start_time).toFixed(1)}s duration)
        </p>
      </section>

      <aside className="panel panel-pad span-4">
        <h2 className="panel-title">Clip Metadata</h2>
        <div className="list-stack" style={{ marginTop: 12 }}>
          <MetadataRow label="Video" value={video.filename} />
          <MetadataRow label="Video status" value={video.status} />
          <MetadataRow label="Session" value={sessionKindLabel} />
          {video.opponent_team && (
            <MetadataRow label="Opponent" value={video.opponent_team} />
          )}
          {possessionLabel && (
            <MetadataRow label="Possession" value={possessionLabel} />
          )}
          {clip.play_number != null && (
            <MetadataRow label="Play #" value={String(clip.play_number)} />
          )}
          <MetadataRow
            label="Boundaries"
            value={`${clip.start_time.toFixed(1)}s → ${clip.end_time.toFixed(1)}s`}
          />
          {clip.confidence != null && (
            <MetadataRow
              label="Confidence"
              value={`${Math.round(clip.confidence * 100)}%`}
            />
          )}
          <MetadataRow label="Reviewed" value={clip.is_reviewed ? "Yes" : "No"} />
          {video.recorded_at && (
            <MetadataRow
              label="Recorded"
              value={new Date(video.recorded_at).toLocaleString()}
            />
          )}
        </div>

        <h3 className="panel-title" style={{ marginTop: 16 }}>Storage</h3>
        <p className="kicker" style={{ wordBreak: "break-all" }}>
          {clip.storage_uri ?? "Clip not yet rendered to R2."}
        </p>
      </aside>
    </div>
  );
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span className="small-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
