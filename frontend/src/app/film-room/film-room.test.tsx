import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

// Mutable navigation state shared with the hoisted next/navigation mock so each
// test can drive the active ?tab= value before rendering.
const nav = vi.hoisted(() => ({ tab: "" }));

vi.mock("next/link", () => ({
  default: ({ children, ...rest }: React.ComponentProps<"a">) => (
    <a {...rest}>{children}</a>
  ),
}));

vi.mock("next/image", () => ({
  default: () => null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/film-room",
  useSearchParams: () => new URLSearchParams(nav.tab ? `tab=${nav.tab}` : ""),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
  nav.tab = "";
});

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "");
  vi.stubEnv("NEXT_PUBLIC_API_URL", "");
});

async function importHub() {
  vi.resetModules();
  const [{ default: FilmRoomPage }, { AppStateProvider }] = await Promise.all([
    import("./page"),
    import("@/lib/app-state"),
  ]);
  return { FilmRoomPage, AppStateProvider };
}

async function renderHub() {
  const { FilmRoomPage, AppStateProvider } = await importHub();
  render(
    <AppStateProvider>
      <FilmRoomPage />
    </AppStateProvider>,
  );
}

describe("FilmRoomPage", () => {
  test("renders all four consolidated tabs", async () => {
    await renderHub();
    await waitFor(() => {
      expect(screen.getByTestId("film-room-tab-browse")).toBeTruthy();
    });
    expect(screen.getByTestId("film-room-tab-review")).toBeTruthy();
    expect(screen.getByTestId("film-room-tab-clips")).toBeTruthy();
    expect(screen.getByTestId("film-room-tab-upload")).toBeTruthy();
  });

  test("default tab is Browse Film (former Library)", async () => {
    await renderHub();
    // Library view is offline without NEXT_PUBLIC_API_URL.
    await waitFor(() => {
      expect(screen.getByText(/Library unavailable/i)).toBeTruthy();
    });
  });

  test("review tab renders the clip review / tagging view", async () => {
    nav.tab = "review";
    await renderHub();
    await waitFor(() => {
      expect(screen.getByText(/Play Tags & Corrections/i)).toBeTruthy();
    });
  });

  test("clips tab renders the clip library view", async () => {
    nav.tab = "clips";
    await renderHub();
    await waitFor(() => {
      expect(screen.getByText(/Clip Library/i)).toBeTruthy();
    });
  });

  test("upload tab renders the explicit Upload & Process Film view", async () => {
    nav.tab = "upload";
    await renderHub();
    await waitFor(() => {
      expect(screen.getByText(/Upload & Process Film/i)).toBeTruthy();
    });
    // Offline backend → explains what is missing rather than faking data.
    await waitFor(() => {
      expect(screen.getByTestId("processing-empty").textContent).toMatch(
        /Backend offline|Checking for uploaded film/i,
      );
    });
  });
});
