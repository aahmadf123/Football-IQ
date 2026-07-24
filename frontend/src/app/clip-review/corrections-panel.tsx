"use client";

/**
 * Coach corrections side panel (Hudl-lite labeling, Phase 3).
 *
 * Deliberately light: a collapsible form in the Clip Review sidebar offering
 * the practical subset of correction types — no drawing tools. Successful
 * submissions POST to ``/api/v1/corrections`` and feed the nightly learning
 * loop; the backend enforces coach-or-above (viewer/player accounts get a
 * 403), so the panel disables its inputs for those roles and says why instead
 * of letting the request fail.
 *
 * Tracklet references use the same ``T{n}`` tags the overlay canvas draws
 * next to each track marker, so a coach can point at the box they mean.
 */

import { useState } from "react";
import { createCorrection, type CorrectionCreate } from "@/lib/api";
import { useAppState } from "@/lib/app-state";
import { canSubmitCorrections } from "@/lib/roles";
import type { OverlayTracklet } from "@/lib/types";

type CorrectionKind =
  | "player_identity"
  | "formation_tag"
  | "clip_boundary"
  | "event_tag";

const KIND_OPTIONS: ReadonlyArray<{ value: CorrectionKind; label: string }> = [
  { value: "player_identity", label: "Wrong team / jersey number" },
  { value: "formation_tag", label: "Formation is wrong" },
  { value: "clip_boundary", label: "Play boundary is wrong / bad clip" },
  { value: "event_tag", label: "Bad boxes / detection glitch" },
];

type SubmitStatus =
  | { kind: "idle" }
  | { kind: "sent" }
  | { kind: "error"; message: string };

interface Props {
  clipId: string;
  /** Tracklets from the overlays payload (may be empty while ingest runs). */
  tracklets: OverlayTracklet[];
}

export function CorrectionsPanel({ clipId, tracklets }: Props) {
  const { authToken, currentRole } = useAppState();
  const locked = !canSubmitCorrections(currentRole);

  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<CorrectionKind>("player_identity");
  const [trackletId, setTrackletId] = useState("");
  const [team, setTeam] = useState("");
  const [jersey, setJersey] = useState("");
  const [formation, setFormation] = useState("");
  const [startSeconds, setStartSeconds] = useState("");
  const [endSeconds, setEndSeconds] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<SubmitStatus>({ kind: "idle" });

  const clearForm = () => {
    setTrackletId("");
    setTeam("");
    setJersey("");
    setFormation("");
    setStartSeconds("");
    setEndSeconds("");
    setNote("");
  };

  const buildPayload = (): CorrectionCreate | null => {
    const trimmedNote = note.trim();
    switch (kind) {
      case "player_identity": {
        if (!trackletId) return null;
        const corrected: Record<string, unknown> = { tracklet_id: trackletId };
        if (team) corrected.team = team;
        if (jersey.trim() !== "" && Number.isFinite(Number(jersey))) {
          corrected.jersey_number = Number(jersey);
        }
        // Require an actual fix, not just a tracklet reference.
        if (!("team" in corrected) && !("jersey_number" in corrected)) return null;
        const tracklet = tracklets.find((t) => t.id === trackletId);
        return {
          clip_id: clipId,
          correction_type: "player_identity",
          corrected_value: corrected,
          original_value: tracklet
            ? { tracklet_id: tracklet.id, team: tracklet.team_label }
            : null,
          notes: trimmedNote || null,
        };
      }
      case "formation_tag": {
        if (!formation.trim()) return null;
        return {
          clip_id: clipId,
          correction_type: "formation_tag",
          corrected_value: { formation: formation.trim() },
          notes: trimmedNote || null,
        };
      }
      case "clip_boundary": {
        const corrected: Record<string, unknown> = {};
        if (trimmedNote) corrected.note = trimmedNote;
        if (startSeconds.trim() !== "" && Number.isFinite(Number(startSeconds))) {
          corrected.start_seconds = Number(startSeconds);
        }
        if (endSeconds.trim() !== "" && Number.isFinite(Number(endSeconds))) {
          corrected.end_seconds = Number(endSeconds);
        }
        if (Object.keys(corrected).length === 0) return null;
        return {
          clip_id: clipId,
          correction_type: "clip_boundary",
          corrected_value: corrected,
          notes: trimmedNote || null,
        };
      }
      case "event_tag": {
        const corrected: Record<string, unknown> = { issue: "bad_boxes" };
        if (trimmedNote) corrected.note = trimmedNote;
        return {
          clip_id: clipId,
          correction_type: "event_tag",
          corrected_value: corrected,
          notes: trimmedNote || null,
        };
      }
    }
  };

  const payload = buildPayload();

  const submit = async () => {
    if (!payload || locked || submitting) return;
    setSubmitting(true);
    setStatus({ kind: "idle" });
    try {
      await createCorrection(payload, authToken);
      setStatus({ kind: "sent" });
      clearForm();
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setSubmitting(false);
    }
  };

  const disabled = locked || submitting;

  return (
    <div data-testid="corrections-panel" style={{ marginTop: 16 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
        }}
      >
        <h3 className="panel-title">Corrections</h3>
        <button
          type="button"
          className="control-button"
          data-testid="corrections-toggle"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? "Hide" : "Fix something"}
        </button>
      </div>

      {open && (
        <div style={{ marginTop: 8 }}>
          {locked && (
            <p
              data-testid="corrections-role-blocked"
              className="kicker"
              style={{ marginBottom: 8 }}
            >
              Your role can&apos;t submit corrections. Ask a coach or analyst to
              file it.
            </p>
          )}

          <div className="form-control">
            <label htmlFor="correction-kind">What needs fixing?</label>
            <select
              id="correction-kind"
              value={kind}
              disabled={disabled}
              onChange={(e) => {
                setKind(e.target.value as CorrectionKind);
                setStatus({ kind: "idle" });
              }}
            >
              {KIND_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {kind === "player_identity" && (
            <>
              {tracklets.length === 0 ? (
                <p className="kicker" style={{ marginTop: 8 }} data-testid="corrections-no-tracklets">
                  No tracklets on this clip yet — overlays may still be
                  processing.
                </p>
              ) : (
                <div className="form-control" style={{ marginTop: 8 }}>
                  <label htmlFor="correction-tracklet">Player track (T# on the overlay)</label>
                  <select
                    id="correction-tracklet"
                    value={trackletId}
                    disabled={disabled}
                    onChange={(e) => setTrackletId(e.target.value)}
                  >
                    <option value="">Select a track…</option>
                    {tracklets.map((t, i) => (
                      <option key={t.id} value={t.id}>
                        {`T${i + 1} · ${t.team_label ?? "unknown team"}${
                          t.position_group ? ` · ${t.position_group}` : ""
                        }`}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div className="form-control" style={{ marginTop: 8 }}>
                <label htmlFor="correction-team">Correct team</label>
                <select
                  id="correction-team"
                  value={team}
                  disabled={disabled}
                  onChange={(e) => setTeam(e.target.value)}
                >
                  <option value="">Leave unchanged</option>
                  <option value="home">Home (us)</option>
                  <option value="away">Away (opponent)</option>
                </select>
              </div>
              <div className="form-control" style={{ marginTop: 8 }}>
                <label htmlFor="correction-jersey">Correct jersey #</label>
                <input
                  id="correction-jersey"
                  type="number"
                  min={0}
                  max={99}
                  value={jersey}
                  disabled={disabled}
                  onChange={(e) => setJersey(e.target.value)}
                />
              </div>
            </>
          )}

          {kind === "formation_tag" && (
            <div className="form-control" style={{ marginTop: 8 }}>
              <label htmlFor="correction-formation">Correct formation</label>
              <input
                id="correction-formation"
                type="text"
                maxLength={80}
                placeholder="e.g. trips right"
                value={formation}
                disabled={disabled}
                onChange={(e) => setFormation(e.target.value)}
              />
            </div>
          )}

          {kind === "clip_boundary" && (
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <div className="form-control" style={{ flex: 1 }}>
                <label htmlFor="correction-start">Start (s)</label>
                <input
                  id="correction-start"
                  type="number"
                  min={0}
                  step="0.1"
                  value={startSeconds}
                  disabled={disabled}
                  onChange={(e) => setStartSeconds(e.target.value)}
                />
              </div>
              <div className="form-control" style={{ flex: 1 }}>
                <label htmlFor="correction-end">End (s)</label>
                <input
                  id="correction-end"
                  type="number"
                  min={0}
                  step="0.1"
                  value={endSeconds}
                  disabled={disabled}
                  onChange={(e) => setEndSeconds(e.target.value)}
                />
              </div>
            </div>
          )}

          <div className="form-control" style={{ marginTop: 8 }}>
            <label htmlFor="correction-note">
              {kind === "clip_boundary" || kind === "event_tag"
                ? "What's wrong?"
                : "Note (optional)"}
            </label>
            <input
              id="correction-note"
              type="text"
              maxLength={280}
              value={note}
              disabled={disabled}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>

          <button
            type="button"
            className="control-button primary"
            data-testid="correction-submit"
            style={{ marginTop: 10 }}
            disabled={disabled || payload == null}
            onClick={submit}
          >
            {submitting ? "Sending…" : "Send correction"}
          </button>

          {status.kind === "sent" && (
            <p
              data-testid="correction-success"
              className="kicker"
              style={{ marginTop: 8, color: "var(--accent-green, #4ade80)" }}
            >
              Sent — feeds the nightly learning loop.
            </p>
          )}
          {status.kind === "error" && (
            <p
              data-testid="correction-error"
              className="kicker"
              style={{ marginTop: 8, color: "var(--accent-red, #f87171)" }}
            >
              {status.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
