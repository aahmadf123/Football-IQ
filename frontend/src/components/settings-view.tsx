"use client";

/**
 * Settings (extracted from the old page-renderer monolith).
 *
 * Backend-wired: GET/PATCH /api/v1/settings/system for the team system config
 * (now including the auto-process-on-upload switch) and model sensitivity.
 * The old decorative "Legal Taxonomy" and "Pipeline Monitor" mock panels were
 * removed (#96); the jobs list renders real jobs from app-state.
 */

import { useEffect, useRef, useState } from "react";
import { useAppState } from "@/lib/app-state";
import { getSystemSettings, updateSystemSettings } from "@/lib/api";
import { MetricLine } from "@/components/shared/metric";
import type { SystemSettingsResponse } from "@/lib/types";

export function SettingsView() {
  const { authToken, data } = useAppState();
  const [settings, setSettings] = useState<SystemSettingsResponse | null>(null);
  const [draft, setDraft] = useState<SystemSettingsResponse | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState<null | "system_config" | "model_sensitivity">(null);
  const [saveErrors, setSaveErrors] = useState<{
    system_config: string | null;
    model_sensitivity: string | null;
  }>({ system_config: null, model_sensitivity: null });
  const [savedSection, setSavedSection] = useState<null | "system_config" | "model_sensitivity">(
    null,
  );
  const savedIndicatorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (savedIndicatorTimeoutRef.current) {
        clearTimeout(savedIndicatorTimeoutRef.current);
        savedIndicatorTimeoutRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!authToken) {
      setSettings(null);
      setDraft(null);
      setLoadState("idle");
      setLoadError(null);
      setSaving(null);
      setSaveErrors({ system_config: null, model_sensitivity: null });
      setSavedSection(null);
      if (savedIndicatorTimeoutRef.current) {
        clearTimeout(savedIndicatorTimeoutRef.current);
        savedIndicatorTimeoutRef.current = null;
      }
      return;
    }
    let cancelled = false;
    setLoadState("loading");
    setLoadError(null);
    getSystemSettings(authToken)
      .then((s) => {
        if (cancelled) return;
        setSettings(s);
        setDraft(s);
        setLoadState("idle");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [authToken]);

  const save = async (section: "system_config" | "model_sensitivity") => {
    if (!authToken || !draft) return;
    setSaving(section);
    setSaveErrors((cur) => ({ ...cur, [section]: null }));
    setSavedSection(null);
    if (savedIndicatorTimeoutRef.current) {
      clearTimeout(savedIndicatorTimeoutRef.current);
      savedIndicatorTimeoutRef.current = null;
    }
    try {
      const updated = await updateSystemSettings({ [section]: draft[section] }, authToken);
      setSettings(updated);
      setDraft(updated);
      setSavedSection(section);
      savedIndicatorTimeoutRef.current = setTimeout(
        () => setSavedSection((cur) => (cur === section ? null : cur)),
        2500,
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setSaveErrors((cur) => ({ ...cur, [section]: msg }));
    } finally {
      setSaving(null);
    }
  };

  const updateSystemConfig = <K extends keyof SystemSettingsResponse["system_config"]>(
    key: K,
    value: SystemSettingsResponse["system_config"][K],
  ) => {
    setDraft((cur) =>
      cur ? { ...cur, system_config: { ...cur.system_config, [key]: value } } : cur,
    );
  };

  const updateSensitivity = <K extends keyof SystemSettingsResponse["model_sensitivity"]>(
    key: K,
    value: SystemSettingsResponse["model_sensitivity"][K],
  ) => {
    setDraft((cur) =>
      cur ? { ...cur, model_sensitivity: { ...cur.model_sensitivity, [key]: value } } : cur,
    );
  };

  const systemDirty =
    settings != null &&
    draft != null &&
    JSON.stringify(settings.system_config) !== JSON.stringify(draft.system_config);
  const sensitivityDirty =
    settings != null &&
    draft != null &&
    JSON.stringify(settings.model_sensitivity) !== JSON.stringify(draft.model_sensitivity);

  return (
    <div className="content-grid">
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">System Config</h2>
        {loadState === "loading" && (
          <p className="kicker" style={{ marginTop: 12 }}>
            Loading settings…
          </p>
        )}
        {loadState === "error" && (
          <p className="kicker" style={{ marginTop: 12, color: "var(--danger, crimson)" }}>
            {loadError ?? "Failed to load settings."}
          </p>
        )}
        {!authToken && (
          <p className="kicker" style={{ marginTop: 12 }}>
            Sign in to view and edit system settings.
          </p>
        )}
        {draft && (
          <>
            <div className="form-control" style={{ marginTop: 10 }}>
              <label>Team name</label>
              <input
                value={draft.system_config.team_name}
                maxLength={120}
                onChange={(e) => updateSystemConfig("team_name", e.target.value)}
              />
            </div>
            <div className="form-control" style={{ marginTop: 10 }}>
              <label>Capture camera</label>
              <input
                value={draft.system_config.capture_camera}
                maxLength={120}
                onChange={(e) => updateSystemConfig("capture_camera", e.target.value)}
              />
            </div>
            <div className="form-control" style={{ marginTop: 10 }}>
              <label>S3/R2 bucket (display only)</label>
              <input
                value={draft.system_config.storage_bucket}
                maxLength={120}
                onChange={(e) => updateSystemConfig("storage_bucket", e.target.value)}
              />
            </div>
            <div className="form-control" style={{ marginTop: 10 }}>
              <label>Auto-export access</label>
              <select
                value={draft.system_config.auto_export_access}
                onChange={(e) =>
                  updateSystemConfig(
                    "auto_export_access",
                    e.target.value as SystemSettingsResponse["system_config"]["auto_export_access"],
                  )
                }
              >
                <option value="off">Off</option>
                <option value="staff">Staff</option>
                <option value="all">All users</option>
              </select>
            </div>
            <label
              className="form-control"
              style={{ marginTop: 12, display: "flex", flexDirection: "row", alignItems: "center", gap: 10 }}
            >
              <input
                type="checkbox"
                checked={draft.system_config.auto_process_on_upload}
                onChange={(e) =>
                  updateSystemConfig("auto_process_on_upload", e.target.checked)
                }
                data-testid="auto-process-toggle"
                style={{ width: 16, height: 16 }}
              />
              <span>
                Process film automatically on upload
                <span className="kicker" style={{ display: "block", marginTop: 2 }}>
                  When off, uploads wait for a manual Process Film click in the Film Room.
                </span>
              </span>
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
              <button
                className="control-button primary"
                onClick={() => save("system_config")}
                disabled={!systemDirty || saving === "system_config"}
              >
                {saving === "system_config" ? "Saving…" : "Save"}
              </button>
              {savedSection === "system_config" && (
                <span className="kicker" style={{ color: "var(--ok, seagreen)" }}>
                  Saved
                </span>
              )}
            </div>
            {saveErrors.system_config && (
              <p className="kicker" style={{ marginTop: 8, color: "var(--danger, crimson)" }}>
                {saveErrors.system_config}
              </p>
            )}
          </>
        )}
      </section>
      <section className="panel panel-pad span-6">
        <h2 className="panel-title">Model Sensitivity</h2>
        {draft && (
          <>
            {(
              [
                ["boundary_sensitivity", "Boundary sensitivity"],
                ["identity_confidence", "Identity confidence"],
                ["motion_minimum", "Motion minimum"],
                ["pose_review_gate", "Pose review gate"],
              ] as const
            ).map(([key, label]) => (
              <div key={key} className="form-control" style={{ marginTop: 10 }}>
                <label>
                  {label} ({draft.model_sensitivity[key]})
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={draft.model_sensitivity[key]}
                  onChange={(e) => updateSensitivity(key, Number(e.target.value))}
                />
              </div>
            ))}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
              <button
                className="control-button primary"
                onClick={() => save("model_sensitivity")}
                disabled={!sensitivityDirty || saving === "model_sensitivity"}
              >
                {saving === "model_sensitivity" ? "Saving…" : "Save"}
              </button>
              {savedSection === "model_sensitivity" && (
                <span className="kicker" style={{ color: "var(--ok, seagreen)" }}>
                  Saved
                </span>
              )}
            </div>
          </>
        )}
        {saveErrors.model_sensitivity && (
          <p className="kicker" style={{ marginTop: 8, color: "var(--danger, crimson)" }}>
            {saveErrors.model_sensitivity}
          </p>
        )}
        {!authToken && (
          <p className="kicker" style={{ marginTop: 12 }}>
            Sign in to tune model sensitivity.
          </p>
        )}
      </section>
      <section className="panel panel-pad span-12">
        <h2 className="panel-title">Processing Jobs</h2>
        {data.jobs.length === 0 ? (
          <p className="kicker" style={{ marginTop: 12 }}>No jobs yet.</p>
        ) : (
          <div className="list-stack" style={{ marginTop: 12 }}>
            {data.jobs.map((job) => <MetricLine key={job.id} label={job.job_type} value={job.status} />)}
          </div>
        )}
      </section>
    </div>
  );
}
