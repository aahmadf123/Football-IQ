import { expect, test } from "@playwright/test";
import { mockBackend, sampleInboxItem } from "./helpers";

/**
 * Seeded /api/v1/inbox/status response → dashboard Practice Inbox
 * surfaces the row, status, and job summary returned by the backend.
 */
test("practice inbox renders seeded video status", async ({ page }) => {
  await mockBackend(page, {
    "GET /api/v1/videos": [],
    "GET /api/v1/jobs": [],
    "GET /api/v1/self-scout/tendencies": { tendencies: [] },
    "GET /api/v1/inbox/status": [
      sampleInboxItem({
        video_id: "vid-inbox-1",
        filename: "PR_20251015_DRONEA.mp4",
        video_status: "processing",
        succeeded_jobs: 3,
        total_jobs: 6,
        clip_count: 0,
      }),
    ],
  });

  await page.goto("/");

  const inbox = page.locator("section").filter({ hasText: /Practice Inbox/ });
  await expect(inbox).toContainText("PR_20251015_DRONEA.mp4");
  await expect(inbox).toContainText("3/6 jobs");
  await expect(inbox).toContainText(/processing/i);
});
