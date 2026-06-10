// Role-gating tests for the Health & Workload surface (Issue #113).
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("next/link", () => ({
  default: ({ children, ...rest }: React.ComponentProps<"a">) => <a {...rest}>{children}</a>,
}));

vi.mock("next/image", () => ({
  default: () => null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/health-workload",
  useSearchParams: () => new URLSearchParams(""),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.resetModules();
});

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "");
  vi.stubEnv("NEXT_PUBLIC_API_URL", "");
});

async function renderPage() {
  vi.resetModules();
  const [{ default: HealthWorkloadPage }, { AppStateProvider }] = await Promise.all([
    import("./page"),
    import("@/lib/app-state"),
  ]);
  render(
    <AppStateProvider>
      <HealthWorkloadPage />
    </AppStateProvider>,
  );
}

describe("Health & Workload surface gating", () => {
  test("approved role (sportsperformance) sees the surface and disclaimer", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_ROLE", "sportsperformance");
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("health-workload-surface")).toBeTruthy();
    });
    // Non-medical disclaimer is shown verbatim.
    const disclaimer = screen.getByTestId("health-workload-disclaimer");
    expect(disclaimer.textContent).toContain("not a medical device");
    expect(disclaimer.textContent).toContain("predict injury risk");
    // All three placeholder integrations render, marked Not connected.
    expect(screen.getByTestId("hw-integration-wellness").textContent).toContain("Not connected");
    expect(screen.getByTestId("hw-integration-gps_wearables")).toBeTruthy();
    expect(screen.getByTestId("hw-integration-strength_conditioning")).toBeTruthy();
    // No restricted notice for an approved role.
    expect(screen.queryByTestId("health-workload-restricted")).toBeNull();
    // Nav exposes the Health & Workload entry for approved roles.
    const nav = screen.getByRole("navigation", { name: /Football IQ navigation/i });
    expect(within(nav).queryByText("Health & Workload")).toBeTruthy();
  });

  test("non-approved role (coach) is gated and the nav entry is hidden", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_ROLE", "coach");
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("health-workload-restricted")).toBeTruthy();
    });
    // The surface content is not rendered for a non-approved role.
    expect(screen.queryByTestId("health-workload-surface")).toBeNull();
    expect(screen.queryByTestId("health-workload-disclaimer")).toBeNull();
    // Nav hides the Health & Workload entry (the page <h1> title still exists,
    // so we scope the assertion to the navigation landmark).
    const nav = screen.getByRole("navigation", { name: /Football IQ navigation/i });
    expect(within(nav).queryByText("Health & Workload")).toBeNull();
  });

  test("default role (no token, no override) is gated", async () => {
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("health-workload-restricted")).toBeTruthy();
    });
    expect(screen.queryByTestId("health-workload-surface")).toBeNull();
  });
});
