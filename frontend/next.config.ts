import type { NextConfig } from "next";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  output: "export", // static export for Cloudflare Pages
  trailingSlash: true,
  turbopack: {
    root,
  },
  images: {
    unoptimized: true, // required for static export
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "",
    NEXT_PUBLIC_WORKER_URL: process.env.NEXT_PUBLIC_WORKER_URL ?? "",
  },
};

export default nextConfig;
