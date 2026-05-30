import { RouteRedirect } from "@/components/route-redirect";

// ADR 0003: Video & Plays moved into Film Room → Review & Tag Plays.
export default function VideoAndPlaysPage() {
  return <RouteRedirect to="/film-room/?tab=review" label="Opening Film Room → Review & Tag Plays…" />;
}
