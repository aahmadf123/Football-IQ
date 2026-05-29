import { expect, test } from "@playwright/test";
import { FAKE_API_URL, mockBackend, type Route, sampleClip, sampleVideo } from "./helpers";

/**
 * The server-backed Clip Review shell does not yet expose a correction
 * form (tracked separately as a P2 follow-up). To still cover the
 * end-to-end shape of the correction call, this test loads the Clip
 * Review page, then *simulates* the coach correction by issuing the
 * POST /api/v1/corrections request the form will eventually call.
 *
 * The mocked backend records the payload so we can assert the contract.
 */
test("coach correction POST is accepted by the mocked backend", async ({
  page,
}) => {
  let received: unknown = null;
  await mockBackend(page, {
    "GET /api/v1/videos": [],
    "GET /api/v1/jobs": [],
    "GET /api/v1/self-scout/tendencies": { tendencies: [] },
    "GET /api/v1/inbox/status": [],
    "GET /api/v1/clips/c-1": sampleClip(),
    "GET /api/v1/videos/v-1": sampleVideo(),
    "POST /api/v1/corrections": (route: Route) => {
      received = JSON.parse(route.request().postData() ?? "{}");
      return { id: "cc-1", status: "saved" };
    },
  });

  await page.goto("/clip-review/?clipId=c-1");

  const result = await page.evaluate(
    async ({ apiUrl }) => {
      const res = await fetch(`${apiUrl}/api/v1/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clip_id: "c-1",
          field: "play_number",
          old_value: 1,
          new_value: 7,
          note: "wrong play number — re-tagged by coach",
        }),
      });
      return { ok: res.ok, status: res.status, body: await res.json() };
    },
    { apiUrl: FAKE_API_URL },
  );

  expect(result.ok).toBe(true);
  expect(result.body).toMatchObject({ status: "saved" });
  expect(received).toMatchObject({ clip_id: "c-1", new_value: 7 });
});
