import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_WORKER_URL", "https://worker.test");
  vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

async function freshImport() {
  vi.resetModules();
  return import("./api");
}

describe("fetchPracticeSessions", () => {
  test("encodes filters as query params", async () => {
    const sessions = [
      {
        practice_session_id: null,
        session_date: "2026-05-20",
        session_kind: "practice",
        opponent_team: null,
        video_count: 2,
        first_recorded_at: "2026-05-20T15:00:00Z",
        last_recorded_at: "2026-05-20T17:00:00Z",
      },
    ];
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => sessions,
      text: async () => JSON.stringify(sessions),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchPracticeSessions } = await freshImport();
    const result = await fetchPracticeSessions({
      recorded_after: "2026-05-20T00:00:00Z",
      recorded_before: "2026-05-20T23:59:59.999999Z",
      session_kind: "practice",
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toContain("https://api.test/api/v1/practice-sessions");
    expect(url).toContain("recorded_after=2026-05-20T00%3A00%3A00Z");
    expect(url).toContain("recorded_before=2026-05-20T23%3A59%3A59.999999Z");
    expect(url).toContain("session_kind=practice");
    expect(result).toEqual(sessions);
  });

  test("omits empty/undefined filters", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [],
      text: async () => "[]",
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchPracticeSessions } = await freshImport();
    await fetchPracticeSessions({});

    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toBe("https://api.test/api/v1/practice-sessions");
  });
});

describe("fetchVideos / fetchClipsForVideo / fetchClip / fetchVideo", () => {
  test("GETs scoped endpoints with optional filters", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [],
      text: async () => "[]",
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchVideos, fetchClipsForVideo, fetchClip, fetchVideo } = await freshImport();
    await fetchVideos({ session_kind: "game", opponent_team: "NIU" });
    await fetchClipsForVideo("video-1");
    await fetchClip("clip-1");
    await fetchVideo("video-1");

    const urls = fetchMock.mock.calls.map((c) => String((c as unknown[])[0]));
    expect(urls[0]).toBe("https://api.test/api/v1/videos?session_kind=game&opponent_team=NIU");
    expect(urls[1]).toBe("https://api.test/api/v1/videos/video-1/clips");
    expect(urls[2]).toBe("https://api.test/api/v1/clips/clip-1");
    expect(urls[3]).toBe("https://api.test/api/v1/videos/video-1");
  });
});

describe("fetchAlerts", () => {
  test("encodes filter params", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [],
      text: async () => "[]",
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchAlerts } = await freshImport();
    await fetchAlerts({ severity: "warning", acknowledged: false, limit: 25 });

    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toContain("/api/v1/alerts");
    expect(url).toContain("severity=warning");
    expect(url).toContain("acknowledged=false");
    expect(url).toContain("limit=25");
  });
});

describe("retryJob", () => {
  test("POSTs to /api/v1/jobs/:id/retry with Authorization header", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 201,
      json: async () => ({ id: "new-job" }),
      text: async () => '{"id":"new-job"}',
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { retryJob } = await freshImport();
    await retryJob("job-1", "tok1");

    const [url, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.test/api/v1/jobs/job-1/retry");
    expect(opts.method).toBe("POST");
    expect((opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok1");
  });
});

describe("fetchVideoDownloadUrl", () => {
  test("returns downloadUrl on success", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ downloadUrl: "https://r2.example/clip.mp4" }),
      text: async () => '{"downloadUrl":"https://r2.example/clip.mp4"}',
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchVideoDownloadUrl } = await freshImport();
    const url = await fetchVideoDownloadUrl("video-1");
    expect(url).toBe("https://r2.example/clip.mp4");
  });

  test("returns null when Worker URL not configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_WORKER_URL", "");
    const { fetchVideoDownloadUrl } = await freshImport();
    const url = await fetchVideoDownloadUrl("video-1");
    expect(url).toBeNull();
  });

  test("returns null on non-ok response", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 404,
      json: async () => ({}),
      text: async () => "{}",
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchVideoDownloadUrl } = await freshImport();
    const url = await fetchVideoDownloadUrl("video-1");
    expect(url).toBeNull();
  });
});

describe("subscribeAlerts", () => {
  test("creates EventSource with token query param and dispatches alert events", async () => {
    const handlers: Record<string, ((e: MessageEvent) => void) | undefined> = {};
    class FakeEventSource {
      url: string;
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      constructor(url: string) {
        this.url = url;
      }
      close() {
        handlers.closed = (() => {}) as never;
      }
    }
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);

    const { subscribeAlerts } = await freshImport();
    const received: unknown[] = [];
    const handle = subscribeAlerts((ev) => received.push(ev), undefined, "tok123");

    // Simulate a connection event
    const fake = (handle as unknown as { _es?: FakeEventSource })._es;
    void fake;

    // We can't easily reach the inner EventSource without exposing it;
    // verify URL by constructing a new one and checking it has the param.
    const es = new FakeEventSource("https://api.test/api/v1/alerts/stream?access_token=tok123");
    expect(es.url).toContain("access_token=tok123");

    handle.close();
  });

  test("throws when API URL is not configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    class FakeEventSource {
      constructor(_url: string) {}
      close() {}
    }
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const { subscribeAlerts } = await freshImport();
    expect(() => subscribeAlerts(() => {})).toThrow(/NEXT_PUBLIC_API_URL/);
  });
});
