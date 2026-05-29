import { expect, test } from "@playwright/test";
import { mockBackend } from "./helpers";

/**
 * Smoke test: the app boots, renders the football shell, and links to the
 * Library and Practice Inbox without crashing. All backend calls are
 * mocked as empty so the shell renders against a known-empty state.
 */
test("dashboard loads with empty backend responses", async ({ page }) => {
  await mockBackend(page, {
    "GET /api/v1/videos": [],
    "GET /api/v1/jobs": [],
    "GET /api/v1/self-scout/tendencies": { tendencies: [] },
    "GET /api/v1/inbox/status": [],
  });

  await page.goto("/");

  // Football-IQ shell always renders the Library nav link.
  await expect(page.getByRole("link", { name: /Library/ })).toBeVisible();
  // No JS crash means the dashboard rendered at least the Practice Inbox.
  await expect(
    page.getByRole("heading", { name: /Practice Inbox/ }),
  ).toBeVisible();
});
