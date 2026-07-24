"use client";

/**
 * Client-upload status list — the single rendering of in-browser upload
 * progress (previously duplicated between the page shell and the Film Room
 * upload tab). One `phaseLabel` / `phaseColor` mapping lives here.
 */

import { Trash2 } from "lucide-react";
import { useAppState, type UploadedClip, type UploadPhase } from "@/lib/app-state";

export function phaseLabel(phase: UploadPhase): string {
  switch (phase) {
    case "idle":
      return "Queued to upload";
    case "requesting-url":
      return "Preparing…";
    case "uploading":
      return "Uploading…";
    case "registering":
      return "Saving…";
    case "done":
      return "Uploaded";
    case "error":
      return "Upload failed";
  }
}

export function phaseColor(phase: UploadPhase): string {
  switch (phase) {
    case "done":
      return "var(--accent-green, #4ade80)";
    case "error":
      return "var(--accent-red, #f87171)";
    case "uploading":
    case "registering":
    case "requesting-url":
      return "var(--accent-amber, #fbbf24)";
    default:
      return "var(--text-muted, #94a3b8)";
  }
}

export function UploadStatusList({ uploads }: { uploads: UploadedClip[] }) {
  const { retryUpload, removeUpload } = useAppState();
  if (uploads.length === 0) return null;
  return (
    <div className="list-stack" style={{ marginTop: 10 }}>
      {uploads.map((u) => (
        <div
          key={u.id}
          className="status-row"
          style={{ gridTemplateColumns: "1fr auto auto" }}
        >
          <div>
            <strong>{u.filename}</strong>
            <div className="kicker">
              {(u.sizeBytes / (1024 * 1024)).toFixed(1)} MB{" · "}
              <span style={{ color: phaseColor(u.phase), fontWeight: 700 }}>
                {phaseLabel(u.phase)}
                {u.phase === "uploading" && ` ${u.progress}%`}
              </span>
            </div>
            {u.phase === "uploading" && (
              <div style={{ height: 3, background: "var(--line-soft, #333)", borderRadius: 2, marginTop: 4 }}>
                <div
                  style={{
                    height: "100%",
                    width: `${u.progress}%`,
                    background: "var(--accent-amber, #fbbf24)",
                    borderRadius: 2,
                    transition: "width 0.3s",
                  }}
                />
              </div>
            )}
            {u.phase === "error" && u.error && (
              <div className="kicker" style={{ color: "var(--accent-red, #f87171)", marginTop: 2 }}>
                {u.error}
              </div>
            )}
          </div>
          {u.phase === "error" && (
            <button className="control-button" onClick={() => retryUpload(u.id)}>
              Retry upload
            </button>
          )}
          <button
            className="control-button"
            onClick={() => removeUpload(u.id)}
            aria-label={`Remove ${u.filename}`}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
