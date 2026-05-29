import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/alerts",
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
  const [{ default: AlertsPage }, { AppStateProvider }] = await Promise.all([
    import("./page"),
    import("@/lib/app-state"),
  ]);
  return { AlertsPage, AppStateProvider };
}

interface RouteSpec {
  url: string;
  body: unknown;
  ok?: boolean;
  status?: number;
}

function installFetchRoutes(routes: RouteSpec[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    for (const r of routes) {
      if (url.includes(r.url)) {
        const ok = r.ok ?? true;
        return {
          ok,
          status: r.status ?? (ok ? 200 : 500),
          json: async () => r.body,
          text: async () => JSON.stringify(r.body),
          body: null,
        } as unknown as Response;
      }
    }
    return {
      ok: true,
      status: 200,
      json: async () => [],
      text: async () => "[]",
      body: null,
    } as unknown as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function tendencyAlert(overrides: Record<string, unknown> = {}) {
  return {
    id: "al-1",
    player_id: null,
    clip_id: null,
    position_group: "OFFENSE",
    alert_type: "formation_tendency",
    severity: "high",
    confidence: 0.8,
    metric_name: "Trips · 11 pers · red zone · 3-long",
    metric_value: {
      tendency_kind: "season_tendency",
      message: "Trips red zone 3-long: 90% pass on 10 plays.",
      evidence_clip_ids: ["clip-a", "clip-b"],
    },
    deviation_sd: null,
    clip_uri: null,
    period_name: null,
    session_id: "season",
    job_id: null,
    is_acknowledged: false,
    acknowledged_by: null,
    acknowledged_at: null,
    is_actioned: false,
    actioned_by: null,
    actioned_at: null,
    created_at: "2026-05-26T12:00:00Z",
    ...overrides,
  };
}

describe("AlertsPage tendency-break rendering", () => {
  test("renders a formation_tendency alert with its message and evidence clips", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    installFetchRoutes([
      { url: "/api/v1/alerts/stream", body: "", ok: false, status: 500 },
      { url: "/api/v1/alerts", body: [tendencyAlert()] },
    ]);

    const { AlertsPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <AlertsPage />
      </AppStateProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Trips red zone 3-long: 90% pass on 10 plays.")).toBeTruthy();
    });
    // "Tendency break" title + evidence clip links.
    expect(screen.getByText("Tendency break")).toBeTruthy();
    expect(screen.getByText("clip 1")).toBeTruthy();
  });

  test("pattern_break alert carries an experimental badge", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    installFetchRoutes([
      { url: "/api/v1/alerts/stream", body: "", ok: false, status: 500 },
      {
        url: "/api/v1/alerts",
        body: [
          tendencyAlert({
            id: "al-2",
            metric_value: {
              tendency_kind: "pattern_break",
              message: "This game is 40% more pass-heavy than the season baseline.",
              evidence_clip_ids: [],
            },
          }),
        ],
      },
    ]);

    const { AlertsPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <AlertsPage />
      </AppStateProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("experimental-badge")).toBeTruthy();
    });
  });

  test("Mark actioned PATCHes and reflects the actioned state", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.test");
    installFetchRoutes([
      { url: "/api/v1/alerts/stream", body: "", ok: false, status: 500 },
      // The action PATCH route is matched before the list route.
      { url: "/api/v1/alerts/al-1/action", body: tendencyAlert({ is_actioned: true }) },
      { url: "/api/v1/alerts", body: [tendencyAlert()] },
    ]);

    const { AlertsPage, AppStateProvider } = await importPage();
    render(
      <AppStateProvider>
        <AlertsPage />
      </AppStateProvider>,
    );

    const button = await screen.findByTestId("action-al-1");
    await act(async () => {
      fireEvent.click(button);
    });

    await waitFor(() => {
      expect(screen.queryByTestId("action-al-1")).toBeNull();
    });
  });
});
