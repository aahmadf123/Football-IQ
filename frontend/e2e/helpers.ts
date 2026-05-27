/**
 * Shared helpers for the Football-IQ E2E suite.
 *
 * The suite intercepts every request to the fake API/Worker hosts declared
 * in `playwright.config.ts`. Helpers here keep individual specs small and
 * make it obvious which backend endpoints each test exercises.
 */
import type { Page, Route } from "@playwright/test";

export type { Route };
export const FAKE_API_URL = "http://api.e2e.local";
export const FAKE_WORKER_URL = "http://worker.e2e.local";

export type JsonHandler = (route: Route) => unknown | Promise<unknown>;

interface RouteMap {
  // Map of `METHOD path` (path may include a trailing wildcard) to a handler
  // that returns the JSON body, or a function for custom routing.
  [route: string]: unknown | JsonHandler;
}

/**
 * Register JSON responders for backend endpoints. Any unmatched request to
 * the fake API host returns 404 so unintended calls fail visibly.
 */
export async function mockBackend(page: Page, routes: RouteMap): Promise<void> {
  await mockHost(page, "api.e2e.local", routes);
}

/**
 * Register responders for the Cloudflare Worker host (upload-url + signed
 * download URLs + the simulated PUT to R2).
 */
export async function mockWorker(page: Page, routes: RouteMap): Promise<void> {
  await mockHost(page, "worker.e2e.local", routes);
}

async function mockHost(page: Page, hostname: string, routes: RouteMap): Promise<void> {
  await page.route(
    (url) => url.hostname === hostname,
    async (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const key = `${req.method()} ${url.pathname}`;
      const matched = matchRoute(routes, key);
      if (matched === undefined) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: `unmocked ${key}` }),
        });
        return;
      }
      if (typeof matched === "function") {
        const result = await (matched as JsonHandler)(route);
        if (result === undefined) return; // handler called route.fulfill itself
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(result),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(matched),
      });
    },
  );
}

function matchRoute(routes: RouteMap, key: string): unknown | undefined {
  if (key in routes) return routes[key];
  // Allow trailing `*` wildcard matching for nested IDs.
  for (const pattern of Object.keys(routes)) {
    if (pattern.endsWith("*") && key.startsWith(pattern.slice(0, -1))) {
      return routes[pattern];
    }
  }
  return undefined;
}

/** Sample video payload matching the backend's ApiVideo schema. */
export function sampleVideo(overrides: Record<string, unknown> = {}) {
  return {
    id: "v-1",
    filename: "PR_20251001_DRONEA.mp4",
    status: "ready",
    duration_seconds: 120,
    fps: 30,
    width: 1920,
    height: 1080,
    created_at: "2025-10-01T10:00:00Z",
    recorded_at: "2025-10-01T09:30:00Z",
    session_kind: "practice",
    source_type: "drone",
    opponent_team: null,
    practice_session_id: "ps-1",
    our_possession: "offense",
    storage_uri: "r2://raw-video/raw/v-1",
    ...overrides,
  };
}

/** Sample clip payload matching the backend's ApiClip schema. */
export function sampleClip(overrides: Record<string, unknown> = {}) {
  return {
    id: "c-1",
    video_id: "v-1",
    start_time: 12.0,
    end_time: 18.5,
    play_number: 1,
    storage_uri: "r2://clips/clips/c-1.mp4",
    confidence: 0.92,
    is_reviewed: false,
    our_possession: "offense",
    side_of_ball: "offense",
    session_kind: "practice",
    ...overrides,
  };
}

/** Sample practice-session group. */
export function samplePracticeSession(overrides: Record<string, unknown> = {}) {
  return {
    practice_session_id: "ps-1",
    session_date: "2025-10-01",
    session_kind: "practice",
    opponent_team: null,
    video_count: 1,
    ...overrides,
  };
}

/** Sample inbox row matching the backend's VideoInboxItem schema. */
export function sampleInboxItem(overrides: Record<string, unknown> = {}) {
  return {
    video_id: "v-1",
    filename: "PR_20251001_DRONEA.mp4",
    video_status: "ready",
    total_jobs: 6,
    running_jobs: 0,
    succeeded_jobs: 6,
    failed_jobs: 0,
    clip_count: 12,
    calibration_safe_pct: 94,
    latest_error_stage: null,
    latest_error_message: null,
    same_session_job_count: 2,
    pose_pipeline_active: true,
    created_at: "2025-10-01T10:00:00Z",
    ...overrides,
  };
}
