const PRODUCTION_API_URL = "https://football-iq-backend.fly.dev";

/**
 * Resolve the backend origin. Production static exports need a usable default
 * because NEXT_PUBLIC_* values are embedded at build time.
 */
export function apiBase(): string {
  const configured = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/+$/, "");
  if (configured) return configured;
  return process.env.NODE_ENV === "production" ? PRODUCTION_API_URL : "";
}
