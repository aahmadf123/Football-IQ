/**
 * Football-IQ API client — upload pipeline and inbox status.
 *
 * Environment variables consumed (public, browser-safe):
 *   NEXT_PUBLIC_API_URL    — backend base URL (FastAPI)
 *   NEXT_PUBLIC_WORKER_URL — Cloudflare Worker base URL
 */

import type {
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
