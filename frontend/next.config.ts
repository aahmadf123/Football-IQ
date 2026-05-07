import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export", // static export for Cloudflare Pages
  trailingSlash: true,
  images: {
    unoptimized: true, // required for static export
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "",
    NEXT_PUBLIC_WORKER_URL: process.env.NEXT_PUBLIC_WORKER_URL ?? "",
  },
};

export default nextConfig;
