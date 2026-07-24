// Dashboard (Phase 2 consolidation): real backend data only — inbox, recent
// film, jobs with per-stage progress, and alerts. No mock badges, no
// fabricated widgets (repo rule #96).
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/image", () => ({
  default: () => null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
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
  const [{ default: DashboardPage }, { AppStateProvider }] = await Promise.all([
    import("./page"),
    import("@/lib/app-state"),
  ]);
  return { DashboardPage, AppStateProvider };
}

interface RouteSpec {
  url: string;
  body: unknown;
}

function installFetchRoutes(routes: RouteSpec[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    for (const r of routes) {
      if (url.includes(r.url)) {
        return {
          ok: true,
          status: 200,
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
  return fetchMock;
}

const SAMPLE_JOB = {
  id: "job-1",
  job_type: "pipeline",
  status: "running",
  priority: 0,
  pipeline_mode: "nightly",
  is_same_session: false,
  error_stage: null,
  error_message: null,
  nightly_followup_job_id: null,
  progress: {
    ingest: { status: "succeeded" },
    detect: { status: "succeeded" },
    "track:1a2b3c4d": { status: "started" },
    "pose:1a2b3c4d": { status: "skipped" },
  },
  created_at: "2026-07-20T10:00:00Z",
};

const SAMPLE_INBOX_ITEM = {
  video_id: "v-1",
  filename: "PR_20260720_DRONEA.mp4",
  video_status: "processing",
  total_jobs: 6,
  running_jobs: 1,
  succeeded_jobs: 3,
  failed_jobs: 0,
  clip_count: 0,
  preliminary_clip_count: 0,
  calibration_safe_pct: null,
  latest_error_stage: null,
  latest_error_message: null,
  same_session_job_count: 1,
  pose_pipeline_active: true,
  created_at: "2026-07-20T10:00:00Z",
};

const SAMPLE_ALERT = {
  id: "al-1",
  player_id: null,
  clip_id: null,
  position_group: "WR",
  alert_type: "effort_flag",
  severity: "medium",
  confidence: 0.82,
  metric_name: "effort_zscore",
  metric_value: {},
  deviation_sd: null,
  clip_uri: null,
  period_name: null,
  session_id: null,
  job_id: null,
  is_acknowledged: false,
  acknowledged_by: null,
  acknowledged_at: null,
  is_actioned: false,
  actioned_by: null,
  actioned_at: null,
  created_at: "2026-07-20T10:00:00Z",
};

const SAMPLE_VIDEO = {
  id: "v-1",
  filename: "PR_20260720_DRONEA.mp4",
  status: "processing",
  created_at: "2026-07-20T10:00:00Z",
};

describe("DashboardPage — live backend", () => {
  test("renders real inbox, jobs (with per-stage progress), and alerts; no mock badges", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    installFetchRoutes([
      { url: "/api/v1/videos", body: [SAMPLE_VIDEO] },
      { url: "/api/v1/jobs", body: [SAMPLE_JOB] },
      { url: "/api/v1/inbox/status", body: [SAMPLE_INBOX_ITEM] },
      { url: "/api/v1/alerts", body: [SAMPLE_ALERT] },
      { url: "/api/v1/players", body: [] },
      { url: "/api/v1/self-scout/tendencies", body: { pre_snap_tells: [], clip_count: 0 } },
    ]);

    const { DashboardPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <DashboardPage />
      </AppStateProvider>,
    );

    // Practice Inbox + Recent Film show the real backend row (filename
    // appears in both cards).
    await waitFor(() => {
      expect(screen.getAllByText("PR_20260720_DRONEA.mp4").length).toBeGreaterThanOrEqual(2);
    });
    expect(screen.getByText(/3\/6 jobs/)).toBeTruthy();

    // Jobs card renders the pipeline job with its per-stage progress map,
    // clip-suffixed stages folded into their base stage.
    await waitFor(() => {
      expect(screen.getByTestId("job-row-job-1")).toBeTruthy();
    });
    const progress = screen.getByTestId("job-progress-job-1");
    expect(progress.textContent).toContain("ingest");
    expect(progress.textContent).toContain("detect");
    expect(progress.textContent).toContain("track");
    expect(progress.textContent).toContain("✓"); // succeeded stages
    expect(progress.textContent).toContain("●"); // running stage

    // Alerts summary renders the real alert row.
    await waitFor(() => {
      expect(screen.getByText("effort_flag")).toBeTruthy();
    });

    // No mock badges anywhere on the live dashboard.
    expect(screen.queryAllByTestId("mock-badge")).toHaveLength(0);
    // None of the deleted fake widgets resurface.
    expect(screen.queryByText(/Biomechanics/)).toBeNull();
    expect(screen.queryByText(/Formation Recognition/)).toBeNull();
    expect(screen.queryByText(/Effectiveness Summary/)).toBeNull();
  });
});

describe("DashboardPage — job lease/attempt surfacing", () => {
  test("running retries show attempt + worker; failed jobs show attempts burned", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    const retryingJob = {
      ...SAMPLE_JOB,
      id: "job-2",
      progress: null,
      attempt_count: 2,
      leased_by: "gpu-worker-1",
    };
    const failedJob = {
      ...SAMPLE_JOB,
      id: "job-3",
      status: "failed",
      progress: null,
      attempt_count: 3,
      leased_by: null,
      error_stage: "track",
      error_message: "CUDA out of memory",
    };
    installFetchRoutes([
      { url: "/api/v1/videos", body: [SAMPLE_VIDEO] },
      { url: "/api/v1/jobs", body: [SAMPLE_JOB, retryingJob, failedJob] },
      { url: "/api/v1/inbox/status", body: [SAMPLE_INBOX_ITEM] },
      { url: "/api/v1/alerts", body: [] },
      { url: "/api/v1/players", body: [] },
      { url: "/api/v1/self-scout/tendencies", body: { pre_snap_tells: [], clip_count: 0 } },
    ]);

    const { DashboardPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <DashboardPage />
      </AppStateProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("job-row-job-2")).toBeTruthy();
    });
    // First-attempt job without lease info shows no extra line.
    expect(screen.queryByTestId("job-lease-job-1")).toBeNull();
    // Retried running job: attempt count + worker id, one subtle line.
    expect(screen.getByTestId("job-lease-job-2").textContent).toBe(
      "attempt 2 · worker gpu-worker-1",
    );
    // Failed job: attempts burned.
    expect(screen.getByTestId("job-lease-job-3").textContent).toBe(
      "failed after 3 attempts",
    );
  });
});

describe("DashboardPage — offline backend", () => {
  test("shows honest offline states instead of fabricated data", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");

    const { DashboardPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <DashboardPage />
      </AppStateProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Inbox unavailable — backend is offline/)).toBeTruthy();
    });
    expect(screen.getByText(/Jobs unavailable — backend is offline/)).toBeTruthy();
    expect(screen.getByText(/Alerts unavailable — backend is offline/)).toBeTruthy();
    // No fixture rows leak in.
    expect(screen.queryByText(/Practice 5-14 All-22/)).toBeNull();
  });
});
