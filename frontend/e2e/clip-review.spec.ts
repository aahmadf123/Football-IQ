import { expect, test } from "@playwright/test";
import {
  mockBackend,
  mockWorker,
  type Route,
  sampleClip,
  sampleVideo,
} from "./helpers";

/**
 * Clip Review route: loading /clip-review?clipId=c-1 must
 *   1. fetch the clip + its parent video from the backend,
 *   2. resolve a signed download URL from the Worker,
 *   3. render a <video> element whose src is the signed URL.
 *
 * The Worker download endpoint is observed and asserted on so this test
 * verifies the upload→inbox→review path actually exercises the signed
 * R2 download flow (not just static markup).
 */
test("clip review opens and invokes the signed download URL path", async ({
  page,
}) => {
  const signedUrl = "https://signed.e2e.local/play.mp4?token=abc";

  let downloadInvoked = false;
  await mockWorker(page, {
    "GET /api/v1/videos/download-url": (route: Route) => {
      downloadInvoked = true;
      const url = new URL(route.request().url());
      expect(url.searchParams.get("bucket")).toBeTruthy();
      expect(url.searchParams.get("key")).toBeTruthy();
      return { downloadUrl: signedUrl };
    },
  });

  await mockBackend(page, {
    "GET /api/v1/videos": [],
    "GET /api/v1/jobs": [],
    "GET /api/v1/self-scout/tendencies": { tendencies: [] },
    "GET /api/v1/inbox/status": [],
    "GET /api/v1/clips/c-1": sampleClip(),
    "GET /api/v1/videos/v-1": sampleVideo(),
  });

  await page.goto("/clip-review/?clipId=c-1");

  const video = page.locator("video");
  await expect(video).toBeVisible();
  await expect(video).toHaveAttribute("src", signedUrl);
  expect(downloadInvoked).toBe(true);
});
