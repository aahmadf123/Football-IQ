/**
 * Cloudflare R2 helpers — upload proxy and download URL generation.
 *
 * Upload flow:
 *   1. Client calls POST /api/v1/videos/upload-url → { uploadUrl, key }
 *   2. Client PUTs the file body to the returned uploadUrl (Worker proxy)
 *   3. Worker writes the body to the R2 bucket via its binding
 *
 * Download flow:
 *   - GET /api/v1/videos/:videoId/download still returns a synthetic URL
 *     (future: real presigned S3-compat URL).
 */

import type { Env } from "./types.js";

export type R2BucketName = "raw-video" | "clips" | "overlays" | "artifacts";

export function getBucket(env: Env, bucketName: R2BucketName): R2Bucket {
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
 * Build the Worker proxy upload URL for a given key.
 * The frontend PUTs the file body directly to this URL.
 */
export function buildUploadProxyUrl(requestUrl: string, key: string): string {
  const base = new URL(requestUrl);
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");
  return `${base.origin}/api/v1/videos/upload/${encodedKey}`;
}

/**
 * Write a request body directly to R2 via the Worker binding.
 */
export async function putObject(
  env: Env,
  bucketName: R2BucketName,
  key: string,
  body: ReadableStream | ArrayBuffer | null,
  contentType?: string,
): Promise<R2Object> {
  const bucket = getBucket(env, bucketName);
  const httpMetadata: R2HTTPMetadata = {};
  if (contentType) {
    httpMetadata.contentType = contentType;
  }
  return bucket.put(key, body, { httpMetadata });
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
  const head = await bucket.head(key);
  if (!head) {
    throw new Response(`Object not found: ${key}`, { status: 404 });
  }
  const url = new URL(`https://r2-proxy.internal/${bucketName}/${key}`);
  url.searchParams.set("action", "download");
  url.searchParams.set("expires", String(Math.floor(Date.now() / 1000) + ttlSeconds));
  return url.toString();
}
