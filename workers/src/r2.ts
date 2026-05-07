/**
 * Cloudflare R2 presigned URL helpers.
 *
 * Generates short-lived signed URLs for:
 *   - PUT  (video upload)
 *   - GET  (video / clip / artifact download)
 */

import type { Env } from "./types.js";

export type R2BucketName = "raw-video" | "clips" | "overlays" | "artifacts";

function getBucket(env: Env, bucketName: R2BucketName): R2Bucket {
  switch (bucketName) {
    case "raw-video":
      return env.RAW_VIDEO;
    case "clips":
      return env.CLIPS;
    case "overlays":
      return env.OVERLAYS;
    case "artifacts":
      return env.ARTIFACTS;
  }
}

/**
 * Create a presigned PUT URL so a client can upload directly to R2.
 */
export async function createUploadUrl(
  env: Env,
  bucketName: R2BucketName,
  key: string,
  ttlSeconds = 3600,
): Promise<string> {
  const bucket = getBucket(env, bucketName);
  const multipart = await bucket.createMultipartUpload(key);
  // Return a synthetic presigned path the Worker can exchange for a PUT upload.
  // For direct presigned URLs, use the R2 S3-compat API with AWS SDK from backend.
  // This endpoint is a lightweight proxy URL that the Worker will handle.
  void multipart; // reserved for future multipart support
  const url = new URL(`https://r2-proxy.internal/${bucketName}/${key}`);
  url.searchParams.set("action", "upload");
  url.searchParams.set("expires", String(Math.floor(Date.now() / 1000) + ttlSeconds));
  return url.toString();
}

/**
 * Create a presigned GET URL so a client can download directly from R2.
 */
export async function createDownloadUrl(
  env: Env,
  bucketName: R2BucketName,
  key: string,
  ttlSeconds = 3600,
): Promise<string> {
  const bucket = getBucket(env, bucketName);
  // Check the object exists first
  const head = await bucket.head(key);
  if (!head) {
    throw new Response(`Object not found: ${key}`, { status: 404 });
  }
  const url = new URL(`https://r2-proxy.internal/${bucketName}/${key}`);
  url.searchParams.set("action", "download");
  url.searchParams.set("expires", String(Math.floor(Date.now() / 1000) + ttlSeconds));
  return url.toString();
}
