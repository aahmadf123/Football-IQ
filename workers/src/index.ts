/**
 * Football-IQ Cloudflare Worker — edge API entrypoint.
 *
 * Routes:
 *   GET  /health                          → liveness probe (no auth)
 *   POST /api/v1/videos/upload-url        → presigned R2 PUT URL
 *   GET  /api/v1/videos/:videoId/download → presigned R2 GET URL
 *   POST /api/v1/jobs                     → submit video processing job
 *
 * All /api/* routes require a valid Bearer JWT issued by the backend.
 */

import { extractBearerToken, verifyJwt } from "./auth.js";
import { createDownloadUrl, createUploadUrl } from "./r2.js";
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
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Max-Age": "86400",
  };
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
      return json({ status: "ok" });
    }

    // ── Auth gate for all /api/* routes ───────────────────────────────────
    if (url.pathname.startsWith("/api/")) {
      const token = extractBearerToken(request);
      if (!token) {
        return json({ error: "Missing authorization header" }, 401);
      }
      try {
        await verifyJwt(token, env.JWT_SECRET);
      } catch (err) {
        if (err instanceof Response) return err;
        return json({ error: "Authentication failed" }, 401);
      }
    }

    // ── POST /api/v1/videos/upload-url ────────────────────────────────────
    if (url.pathname === "/api/v1/videos/upload-url" && request.method === "POST") {
      const body = (await request.json()) as { filename: string; ttl?: number };
      if (!body.filename) {
        return json({ error: "filename is required" }, 400);
      }
      const key = `raw/${Date.now()}-${body.filename}`;
      const uploadUrl = await createUploadUrl(env, "raw-video", key, body.ttl ?? 3600);
      return json({ uploadUrl, key }, 200);
    }

    // ── GET /api/v1/videos/:videoId/download ──────────────────────────────
    const downloadMatch = url.pathname.match(/^\/api\/v1\/videos\/([^/]+)\/download$/);
    if (downloadMatch && request.method === "GET") {
      const key = `raw/${downloadMatch[1]}`;
      try {
        const downloadUrl = await createDownloadUrl(env, "raw-video", key);
        return json({ downloadUrl });
      } catch (err) {
        if (err instanceof Response) return err;
        return json({ error: "Could not generate download URL" }, 500);
      }
    }

    // ── POST /api/v1/jobs ─────────────────────────────────────────────────
    if (url.pathname === "/api/v1/jobs" && request.method === "POST") {
      const body = (await request.json()) as {
        jobId: string;
        videoId: string;
        jobType: string;
        priority?: number;
        inputUri: string;
      };
      if (!body.jobId || !body.videoId || !body.jobType || !body.inputUri) {
        return json({ error: "jobId, videoId, jobType, and inputUri are required" }, 400);
      }
      await enqueueVideoProcessingJob(env, {
        jobId: body.jobId,
        videoId: body.videoId,
        jobType: body.jobType,
        priority: body.priority ?? 0,
        inputUri: body.inputUri,
        submittedAt: new Date().toISOString(),
      });
      return json({ queued: true, jobId: body.jobId }, 202);
    }

    return json({ error: "Not found" }, 404);
  },
};
