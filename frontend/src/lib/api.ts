/**
 * Football-IQ API client — upload pipeline, library, inbox, alerts, clips.
 *
 * Environment variables consumed (public, browser-safe):
 *   NEXT_PUBLIC_API_URL    — backend base URL (FastAPI)
 *   NEXT_PUBLIC_WORKER_URL — Cloudflare Worker base URL
 */

import type {
  ApiClip,
  ApiPlayer,
  ApiPracticeSessionGroup,
  ApiVideo,
  ClipOverlayPayload,
  OpponentSummary,
  SelfScoutResponse,
  SessionKind,
  SourceType,
  OurPossession,
} from "./types";

// ── Helpers ──────────────────────────────────────────────────────────────────

function workerBase(): string {
  return process.env.NEXT_PUBLIC_WORKER_URL ?? "";
}

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "";
}

function authHeaders(token?: string): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

function getHeaders(token?: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function getJSON<T>(url: string, token?: string): Promise<T> {
  const res = await fetch(url, { headers: getHeaders(token) });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GET ${url} failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<T>;
}

// ── Upload URL ───────────────────────────────────────────────────────────────

export interface UploadUrlResponse {
  uploadUrl: string;
  key: string;
}

export async function requestUploadUrl(
  filename: string,
  token?: string,
): Promise<UploadUrlResponse> {
  const base = workerBase();
  if (!base) throw new Error("NEXT_PUBLIC_WORKER_URL is not configured");
  const res = await fetch(`${base}/api/v1/videos/upload-url`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ filename }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to get upload URL (${res.status}): ${body}`);
  }
  return res.json() as Promise<UploadUrlResponse>;
}

// ── R2 Upload ────────────────────────────────────────────────────────────────

export interface R2UploadResult {
  key: string;
  size: number;
  etag: string;
  storageUri: string;
}

export async function uploadToR2(
  uploadUrl: string,
  file: File,
  token?: string,
  onProgress?: (loaded: number, total: number) => void,
): Promise<R2UploadResult> {
  if (onProgress && typeof XMLHttpRequest !== "undefined") {
    return uploadWithXhr(uploadUrl, file, token, onProgress);
  }
  const headers: Record<string, string> = {
    "Content-Type": file.type || "video/mp4",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers,
    body: file,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`R2 upload failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<R2UploadResult>;
}

function uploadWithXhr(
  url: string,
  file: File,
  token: string | undefined,
  onProgress: (loaded: number, total: number) => void,
): Promise<R2UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type || "video/mp4");
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress(e.loaded, e.total);
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as R2UploadResult);
        } catch {
          reject(new Error("Invalid JSON response from R2 upload"));
        }
      } else {
        reject(new Error(`R2 upload failed (${xhr.status}): ${xhr.responseText}`));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("R2 upload network error")));
    xhr.addEventListener("abort", () => reject(new Error("R2 upload aborted")));
    xhr.send(file);
  });
}

// ── Video Registration ───────────────────────────────────────────────────────

export interface RegisterVideoRequest {
  filename: string;
  storage_uri: string;
  recorded_at?: string | null;
  session_kind?: SessionKind | null;
  source_type?: SourceType | null;
  opponent_team?: string | null;
  practice_session_id?: string | null;
  our_possession?: OurPossession | null;
}

export async function registerVideo(
  data: RegisterVideoRequest,
  token?: string,
): Promise<ApiVideo> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const res = await fetch(`${base}/api/v1/videos`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Video registration failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<ApiVideo>;
}

// ── Inbox Status ─────────────────────────────────────────────────────────────

export interface VideoInboxItem {
  video_id: string;
  filename: string;
  video_status: string;
  total_jobs: number;
  running_jobs: number;
  succeeded_jobs: number;
  failed_jobs: number;
  clip_count: number;
  calibration_safe_pct: number | null;
  latest_error_stage: string | null;
  latest_error_message: string | null;
  same_session_job_count: number;
  pose_pipeline_active: boolean;
  created_at: string;
}

export async function fetchInboxStatus(
  token?: string,
  includeSucceeded = false,
): Promise<VideoInboxItem[]> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const params = new URLSearchParams();
  if (includeSucceeded) params.set("include_succeeded", "true");
  const qs = params.toString();
  const url = `${base}/api/v1/inbox/status${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { headers: authHeaders(token) });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Inbox status failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<VideoInboxItem[]>;
}

// ── Library: practice sessions and videos ─────────────────────────────────────

export interface PracticeSessionFilters {
  recorded_after?: string;
  recorded_before?: string;
  session_kind?: SessionKind;
  opponent_team?: string;
  limit?: number;
}

export async function fetchPracticeSessions(
  filters: PracticeSessionFilters = {},
  token?: string,
): Promise<ApiPracticeSessionGroup[]> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return getJSON<ApiPracticeSessionGroup[]>(
    `${base}/api/v1/practice-sessions${qs ? `?${qs}` : ""}`,
    token,
  );
}

export interface VideoFilters {
  recorded_after?: string;
  recorded_before?: string;
  session_kind?: SessionKind;
  source_type?: SourceType;
  opponent_team?: string;
  practice_session_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export async function fetchVideos(
  filters: VideoFilters = {},
  token?: string,
): Promise<ApiVideo[]> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return getJSON<ApiVideo[]>(
    `${base}/api/v1/videos${qs ? `?${qs}` : ""}`,
    token,
  );
}

export async function fetchVideo(videoId: string, token?: string): Promise<ApiVideo> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  return getJSON<ApiVideo>(`${base}/api/v1/videos/${videoId}`, token);
}

export async function fetchClipsForVideo(
  videoId: string,
  token?: string,
): Promise<ApiClip[]> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  return getJSON<ApiClip[]>(`${base}/api/v1/videos/${videoId}/clips`, token);
}

export async function fetchClip(clipId: string, token?: string): Promise<ApiClip> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  return getJSON<ApiClip>(`${base}/api/v1/clips/${clipId}`, token);
}

// ── Clip overlays (Issue #104) ───────────────────────────────────────────────

export async function fetchClipOverlays(
  clipId: string,
  token?: string,
): Promise<ClipOverlayPayload> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  return getJSON<ClipOverlayPayload>(
    `${base}/api/v1/clips/${clipId}/overlays`,
    token,
  );
}

// ── Self-Scout + Opponent Scout (Issue #105) ─────────────────────────────────

export async function fetchSelfScoutTendencies(
  videoId?: string | null,
  token?: string,
  limit?: number,
): Promise<SelfScoutResponse> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const params = new URLSearchParams();
  if (videoId) params.set("video_id", videoId);
  if (limit != null) params.set("limit", String(limit));
  const qs = params.toString();
  return getJSON<SelfScoutResponse>(
    `${base}/api/v1/self-scout/tendencies${qs ? `?${qs}` : ""}`,
    token,
  );
}

export async function fetchOpponentTendencies(
  opponentVideoId: string,
  token?: string,
  limit?: number,
): Promise<SelfScoutResponse> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const params = new URLSearchParams({ opponent_video_id: opponentVideoId });
  if (limit != null) params.set("limit", String(limit));
  return getJSON<SelfScoutResponse>(
    `${base}/api/v1/self-scout/opponent-tendencies?${params.toString()}`,
    token,
  );
}

export async function fetchOpponents(token?: string): Promise<OpponentSummary[]> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  return getJSON<OpponentSummary[]>(`${base}/api/v1/opponents`, token);
}

// ── Players ──────────────────────────────────────────────────────────────────

export interface PlayerFilters {
  position?: string;
  position_group?: string;
  is_active?: boolean;
  jersey_number?: number;
  search?: string;
  limit?: number;
  offset?: number;
}

export async function fetchPlayers(
  filters: PlayerFilters = {},
  token?: string,
): Promise<ApiPlayer[]> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return getJSON<ApiPlayer[]>(
    `${base}/api/v1/players${qs ? `?${qs}` : ""}`,
    token,
  );
}

export async function fetchPlayer(playerId: string, token?: string): Promise<ApiPlayer> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  return getJSON<ApiPlayer>(`${base}/api/v1/players/${playerId}`, token);
}

// ── Jobs ─────────────────────────────────────────────────────────────────────

export async function retryJob(jobId: string, token?: string): Promise<unknown> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const res = await fetch(`${base}/api/v1/jobs/${jobId}/retry`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Job retry failed (${res.status}): ${body}`);
  }
  return res.json();
}

// ── Alerts ───────────────────────────────────────────────────────────────────

export interface ApiAlert {
  id: string;
  player_id: string | null;
  clip_id: string | null;
  position_group: string;
  alert_type: string;
  severity: string;
  confidence: number;
  metric_name: string;
  metric_value: Record<string, unknown>;
  deviation_sd: number | null;
  clip_uri: string | null;
  period_name: string | null;
  session_id: string | null;
  job_id: string | null;
  is_acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  created_at: string;
}

export interface AlertFilters {
  alert_type?: string;
  severity?: string;
  session_id?: string;
  acknowledged?: boolean;
  limit?: number;
  offset?: number;
}

export async function fetchAlerts(
  filters: AlertFilters = {},
  token?: string,
): Promise<ApiAlert[]> {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return getJSON<ApiAlert[]>(
    `${base}/api/v1/alerts${qs ? `?${qs}` : ""}`,
    token,
  );
}

export type AlertStreamEvent =
  | { type: "alert"; alert: ApiAlert }
  | { type: "connected"; connection_id?: string }
  | { type: "keepalive" };

export interface AlertStreamHandle {
  close: () => void;
}

/**
 * Subscribe to the alert stream via SSE.
 *
 * Uses fetch + ReadableStream (not native EventSource) so we can set the
 * `Authorization: Bearer <token>` header that the backend `HTTPBearer`
 * dependency requires. Access tokens are deliberately NOT placed in the URL
 * (avoids leakage via logs, browser history, and referrers).
 */
export function subscribeAlerts(
  onEvent: (event: AlertStreamEvent) => void,
  onError?: (err: Event | Error) => void,
  token?: string,
): AlertStreamHandle {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  if (typeof fetch === "undefined" || typeof AbortController === "undefined") {
    throw new Error("fetch/AbortController are not available in this environment");
  }

  const controller = new AbortController();
  let closed = false;
  const url = `${base}/api/v1/alerts/stream`;
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const dispatch = (raw: string) => {
    try {
      const data = JSON.parse(raw) as Record<string, unknown>;
      if (data.type === "connected") {
        onEvent({ type: "connected", connection_id: data.connection_id as string });
      } else if (data.type === "keepalive") {
        onEvent({ type: "keepalive" });
      } else {
        onEvent({ type: "alert", alert: data as unknown as ApiAlert });
      }
    } catch (err) {
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  };

  (async () => {
    try {
      const res = await fetch(url, {
        method: "GET",
        headers,
        credentials: "include",
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`SSE connect failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      while (!closed) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE events are separated by a blank line ("\n\n").
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const rawEvent = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          // Concatenate all `data:` lines per the SSE spec.
          const dataLines = rawEvent
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).replace(/^ /, ""));
          if (dataLines.length > 0) dispatch(dataLines.join("\n"));
        }
      }
    } catch (err) {
      if (closed) return;
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  })();

  return {
    close: () => {
      closed = true;
      try { controller.abort(); } catch { /* ignore */ }
    },
  };
}

// ── Worker download URL ──────────────────────────────────────────────────────

/**
 * Parse a storage URI of the form `r2://<bucket>/<key>` into its parts.
 * Returns null if the URI is missing or malformed.
 */
export function parseStorageUri(
  uri: string | null | undefined,
): { bucket: string; key: string } | null {
  if (!uri) return null;
  const m = /^r2:\/\/([^/]+)\/(.+)$/.exec(uri);
  return m ? { bucket: m[1], key: m[2] } : null;
}

/**
 * Extract the R2 key suffix from a backend `storage_uri` of the form
 * `r2://raw-video/raw/<suffix>`. Kept for backward compatibility.
 */
export function r2KeySuffixFromStorageUri(uri: string | null | undefined): string | null {
  if (!uri) return null;
  const m = /^r2:\/\/raw-video\/raw\/(.+)$/.exec(uri);
  return m ? m[1] : null;
}

/**
 * Fetch a signed download/streaming URL for an R2-backed video object.
 * The returned URL can be used directly as a `<video src>`.
 */
export async function fetchVideoDownloadUrl(
  bucket: string,
  key: string,
  token?: string,
): Promise<string | null> {
  const base = workerBase();
  if (!base) return null;
  try {
    const params = new URLSearchParams({ bucket, key });
    const res = await fetch(
      `${base}/api/v1/videos/download-url?${params.toString()}`,
      { headers: getHeaders(token) },
    );
    if (!res.ok) return null;
    const body = (await res.json()) as { downloadUrl?: string };
    return body.downloadUrl ?? null;
  } catch {
    return null;
  }
}
