/**
 * Football-IQ Cloudflare Worker — edge API entrypoint.
 *
 * Routes:
 *   GET  /health                          → liveness probe (no auth)
 *   POST /api/v1/videos/upload-url        → Worker proxy upload URL + R2 key
 *   PUT  /api/v1/videos/upload/*          → proxy PUT to R2 raw-video bucket
 *   GET  /api/v1/videos/:videoId/download → presigned R2 GET URL
 *   POST /api/v1/jobs                     → submit video processing job
 *
 * All /api/* routes require a valid Bearer JWT issued by the backend.
 */

import { extractBearerToken, verifyJwt } from "./auth.js";
import { buildUploadProxyUrl, createDownloadUrl, putObject } from "./r2.js";
import { enqueueVideoProcessingJob } from "./queue.js";
import type { Env } from "./types.js";

// ── Response helpers ──────────────────────────────────────────────────────────

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function corsHeaders(origin: string): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

function withCors(response: Response, cors: Record<string, string>): Response {
  const headers = new Headers(response.headers);
  for (const [k, v] of Object.entries(cors)) {
    headers.set(k, v);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

// ── Router ───────────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") ?? "*";
    const cors = corsHeaders(origin);

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    // ── Liveness probe ────────────────────────────────────────────────────
    if (url.pathname === "/health" && request.method === "GET") {
      return withCors(json({ status: "ok" }), cors);
    }

    // ── Auth gate for all /api/* routes ───────────────────────────────────
    if (url.pathname.startsWith("/api/")) {
      const token = extractBearerToken(request);
      if (!token) {
        return withCors(json({ error: "Missing authorization header" }, 401), cors);
      }
      try {
        await verifyJwt(token, env.JWT_SECRET);
      } catch (err) {
        if (err instanceof Response) return withCors(err, cors);
        return withCors(json({ error: "Authentication failed" }, 401), cors);
      }
    }

    // ── POST /api/v1/videos/upload-url ────────────────────────────────────
    if (url.pathname === "/api/v1/videos/upload-url" && request.method === "POST") {
      const body = (await request.json()) as { filename: string };
      if (!body.filename) {
        return withCors(json({ error: "filename is required" }, 400), cors);
      }
      const key = `raw/${Date.now()}-${body.filename}`;
      const uploadUrl = buildUploadProxyUrl(request.url, key);
      return withCors(json({ uploadUrl, key }), cors);
    }

    // ── PUT /api/v1/videos/upload/* ───────────────────────────────────────
    const uploadMatch = url.pathname.match(/^\/api\/v1\/videos\/upload\/(.+)$/);
    if (uploadMatch && request.method === "PUT") {
      const key = decodeURIComponent(uploadMatch[1]);
      if (!key) {
        return withCors(json({ error: "Missing upload key" }, 400), cors);
      }
      try {
        const contentType = request.headers.get("Content-Type") ?? "video/mp4";
        const obj = await putObject(env, "raw-video", key, request.body, contentType);
        return withCors(json({
          key,
          size: obj.size,
          etag: obj.etag,
          storageUri: `r2://raw-video/${key}`,
        }, 201), cors);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        return withCors(json({ error: message }, 500), cors);
      }
    }

    // ── GET /api/v1/videos/:videoId/download ──────────────────────────────
    const downloadMatch = url.pathname.match(/^\/api\/v1\/videos\/([^/]+)\/download$/);
    if (downloadMatch && request.method === "GET") {
      const key = `raw/${downloadMatch[1]}`;
      try {
        const downloadUrl = await createDownloadUrl(env, "raw-video", key);
        return withCors(json({ downloadUrl }), cors);
      } catch (err) {
        if (err instanceof Response) return withCors(err, cors);
        return withCors(json({ error: "Could not generate download URL" }, 500), cors);
      }
    }

    // ── POST /api/v1/jobs ─────────────────────────────────────────────────
    if (url.pathname === "/api/v1/jobs" && request.method === "POST") {
      const body = (await request.json()) as {
        jobId: string;
        videoId: string;
        jobType: string;
        priority?: number;
        pipelineMode?: "same_session" | "nightly";
        inputUri: string;
      };
      if (!body.jobId || !body.videoId || !body.jobType || !body.inputUri) {
        return withCors(json({ error: "jobId, videoId, jobType, and inputUri are required" }, 400), cors);
      }
      const priority = body.priority ?? 0;
      await enqueueVideoProcessingJob(env, {
        jobId: body.jobId,
        videoId: body.videoId,
        jobType: body.jobType,
        priority,
        pipelineMode: body.pipelineMode,
        inputUri: body.inputUri,
        submittedAt: new Date().toISOString(),
      });
      const isSameSession = priority >= 10;
      return withCors(json({
        queued: true,
        jobId: body.jobId,
        pipelineMode: isSameSession ? "same_session" : "nightly",
        queue: isSameSession ? "same-session-jobs" : "video-processing-jobs",
      }, 202), cors);
    }

    return withCors(json({ error: "Not found" }, 404), cors);
  },
};
