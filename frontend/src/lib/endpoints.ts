/**
 * Resolve the backend origin. Production static exports need a usable default
 * because NEXT_PUBLIC_* values are embedded at build time.
 *
 * In production, default to same-origin so Cloudflare Pages can proxy
 * `/api/*` to the backend via `_redirects`, avoiding brittle cross-origin
 * CORS coupling for auth/login flows.
 */
export function apiBase(): string {
  const configured = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/+$/, "");
  if (configured) return configured;
  if (process.env.NODE_ENV === "production" && typeof window !== "undefined") {
    return window.location.origin.replace(/\/+$/, "");
  }
  return "";
}
