import { RouteRedirect } from "@/components/route-redirect";

// ADR 0003: Clips & Highlights moved into Film Room → Clips & Highlights.
export default function ClipsHighlightsPage() {
  return <RouteRedirect to="/film-room/?tab=clips" label="Opening Film Room → Clips & Highlights…" />;
}
