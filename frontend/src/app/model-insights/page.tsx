import { RouteRedirect } from "@/components/route-redirect";

// ADR 0003: "Model Insights" is the coach-facing name for the Analytics
// surface. The canonical route stays /analytics for deep-link stability; this
// alias redirects to it.
export default function ModelInsightsPage() {
  return <RouteRedirect to="/analytics/" label="Opening Model Insights…" />;
}
