/**
 * Football-IQ API client — upload pipeline, library, inbox, alerts, clips.
 *
 * Environment variables consumed (public, browser-safe):
 *   NEXT_PUBLIC_API_URL    — backend base URL (FastAPI)
 *   NEXT_PUBLIC_WORKER_URL — Cloudflare Worker base URL
 */

import type {
  ApiClip,
  ApiPracticeSessionGroup,
  ApiVideo,
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
 * Note: native EventSource cannot set Authorization headers. Auth flows that
 * require a Bearer token must rely on cookies or a token query param the
 * backend accepts. We pass token as a query param when supplied so the
 * backend may use it; if the backend only accepts Authorization headers,
 * the call will be rejected and onError fires — the UI then shows a
 * degraded state and falls back to polling.
 */
export function subscribeAlerts(
  onEvent: (event: AlertStreamEvent) => void,
  onError?: (err: Event | Error) => void,
  token?: string,
): AlertStreamHandle {
  const base = apiBase();
  if (!base) throw new Error("NEXT_PUBLIC_API_URL is not configured");
  if (typeof EventSource === "undefined") {
    throw new Error("EventSource is not available in this environment");
  }
  const params = new URLSearchParams();
  if (token) params.set("access_token", token);
  const qs = params.toString();
  const url = `${base}/api/v1/alerts/stream${qs ? `?${qs}` : ""}`;
  const es = new EventSource(url, { withCredentials: true });

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as Record<string, unknown>;
      if (data.type === "connected") {
        onEvent({ type: "connected", connection_id: data.connection_id as string });
      } else if (data.type === "keepalive") {
        onEvent({ type: "keepalive" });
      } else {
        // Treat unknown payload as an alert dict
        onEvent({ type: "alert", alert: data as unknown as ApiAlert });
      }
    } catch (err) {
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  };
  es.onerror = (e) => onError?.(e);
  return { close: () => es.close() };
}

// ── Worker download URL ──────────────────────────────────────────────────────

export async function fetchVideoDownloadUrl(
  videoIdOrKeySuffix: string,
  token?: string,
): Promise<string | null> {
  const base = workerBase();
  if (!base) return null;
  try {
    const res = await fetch(
      `${base}/api/v1/videos/${encodeURIComponent(videoIdOrKeySuffix)}/download`,
      { headers: getHeaders(token) },
    );
    if (!res.ok) return null;
    const body = (await res.json()) as { downloadUrl?: string };
    return body.downloadUrl ?? null;
  } catch {
    return null;
  }
}
