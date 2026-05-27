import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/image", () => ({
  default: () => null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/self-scout",
}));

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "");
});

async function importPage() {
  vi.resetModules();
  const [{ default: SelfScoutPage }, { AppStateProvider }] = await Promise.all([
    import("./page"),
    import("@/lib/app-state"),
  ]);
  return { SelfScoutPage, AppStateProvider };
}

interface RouteSpec {
  url: string;
  body: unknown;
  ok?: boolean;
  status?: number;
}

function installFetchRoutes(routes: RouteSpec[]) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push(url);
    for (const r of routes) {
      if (url.includes(r.url)) {
        const ok = r.ok ?? true;
        return {
          ok,
          status: r.status ?? (ok ? 200 : 500),
          json: async () => r.body,
          text: async () => JSON.stringify(r.body),
        } as unknown as Response;
      }
    }
    return {
      ok: true,
      status: 200,
      json: async () => [],
      text: async () => "[]",
    } as unknown as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

const SAMPLE_VIDEO = {
  id: "vid-1",
  filename: "practice.mp4",
  status: "ready",
  created_at: "2026-05-20T12:00:00Z",
  recorded_at: "2026-05-20T12:00:00Z",
  session_kind: "practice",
  opponent_team: null,
};

const SAMPLE_TENDENCIES = {
  formation_tendencies: [
    {
      grouping_key: "Trips Right",
      total_plays: 12,
      run_count: 8,
      pass_count: 4,
      run_rate: 0.67,
      pass_rate: 0.33,
      evidence_clip_ids: [],
      low_sample: false,
    },
  ],
  motion_tendencies: {
    with_motion: { total: 5, run_count: 3, pass_count: 2, run_rate: 0.6, pass_rate: 0.4 },
    without_motion: { total: 7, run_count: 5, pass_count: 2, run_rate: 0.71, pass_rate: 0.29 },
  },
  field_zone_tendencies: [],
  personnel_tendencies: [],
  down_distance_tendencies: [],
  formation_concept_families: {},
  pre_snap_tells: [
    {
      grouping_key: "Trips|with_motion",
      formation: "Trips",
      motion_state: "with_motion",
      total_plays: 5,
      lean: "pass",
      severity: "high",
      run_rate: 0.0,
      pass_rate: 1.0,
      evidence_clip_ids: [],
      low_sample: false,
      message: "Trips with motion is a pass tell",
    },
  ],
  alerts: [],
  clip_count: 12,
};

describe("SelfScoutPage", () => {
  test("shows offline state when NEXT_PUBLIC_API_URL is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    const { SelfScoutPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <SelfScoutPage />
      </AppStateProvider>,
    );
    await waitFor(() => {
      expect(screen.getAllByTestId("card-unavailable").length).toBeGreaterThan(0);
    });
  });

  test("renders live tendencies when backend returns data", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    installFetchRoutes([
      { url: "/api/v1/self-scout/tendencies", body: SAMPLE_TENDENCIES },
      { url: "/api/v1/videos", body: [SAMPLE_VIDEO] },
      { url: "/api/v1/players", body: [] },
      { url: "/api/v1/jobs", body: [] },
      { url: "/api/v1/inbox/status", body: [] },
    ]);

    const { SelfScoutPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <SelfScoutPage />
      </AppStateProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Trips Right")).toBeTruthy();
    });
    expect(screen.getByTestId("pre-snap-tell-Trips|with_motion")).toBeTruthy();
  });

  test("renders empty state when backend reports zero clips", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    installFetchRoutes([
      {
        url: "/api/v1/self-scout/tendencies",
        body: { ...SAMPLE_TENDENCIES, formation_tendencies: [], pre_snap_tells: [], clip_count: 0 },
      },
      { url: "/api/v1/videos", body: [] },
      { url: "/api/v1/players", body: [] },
      { url: "/api/v1/jobs", body: [] },
      { url: "/api/v1/inbox/status", body: [] },
    ]);

    const { SelfScoutPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <SelfScoutPage />
      </AppStateProvider>,
    );

    await waitFor(() => {
      // All five cards render in their empty state.
      expect(screen.getAllByTestId("card-empty").length).toBeGreaterThanOrEqual(5);
    });
  });

  test("renders error state when tendencies endpoint fails", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    installFetchRoutes([
      { url: "/api/v1/self-scout/tendencies", body: { detail: "boom" }, ok: false, status: 500 },
      { url: "/api/v1/videos", body: [SAMPLE_VIDEO] },
      { url: "/api/v1/players", body: [] },
      { url: "/api/v1/jobs", body: [] },
      { url: "/api/v1/inbox/status", body: [] },
    ]);

    const { SelfScoutPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <SelfScoutPage />
      </AppStateProvider>,
    );

    await waitFor(() => {
      expect(screen.getAllByTestId("card-error").length).toBeGreaterThan(0);
    });
  });

  test("picker passes selected video_id through to /api/v1/self-scout/tendencies", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    const { fetchMock, calls } = installFetchRoutes([
      { url: "/api/v1/self-scout/tendencies", body: SAMPLE_TENDENCIES },
      { url: "/api/v1/videos", body: [SAMPLE_VIDEO] },
      { url: "/api/v1/players", body: [] },
      { url: "/api/v1/jobs", body: [] },
      { url: "/api/v1/inbox/status", body: [] },
    ]);

    const { SelfScoutPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <SelfScoutPage />
      </AppStateProvider>,
    );

    const picker = await screen.findByTestId<HTMLSelectElement>("self-scout-video-picker");
    await waitFor(() => {
      // Wait until the picker has populated with the backend video.
      expect(picker.options.length).toBeGreaterThan(1);
    });
    const videoFetchesBeforeSelection = calls.filter((c) => c.includes("/api/v1/videos")).length;

    await act(async () => {
      fireEvent.change(picker, { target: { value: "vid-1" } });
    });

    await waitFor(() => {
      const matched = calls.find(
        (c) => c.includes("/api/v1/self-scout/tendencies") && c.includes("video_id=vid-1"),
      );
      expect(matched).toBeTruthy();
    });
    expect(calls.filter((c) => c.includes("/api/v1/videos")).length).toBe(
      videoFetchesBeforeSelection,
    );
    expect(fetchMock).toHaveBeenCalled();
  });
});
