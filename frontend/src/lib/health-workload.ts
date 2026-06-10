// Athlete health/workload surface contracts (Issue #113), mirrored from the
// backend `app.health_workload` module so the UI can render the placeholder
// integration status before a real session/feed exists. The backend
// `GET /api/v1/health-workload/surface` endpoint is the authoritative source
// once an auth/session flow is wired; until then the page renders these
// placeholders statically.

export type IntegrationSource = "wellness" | "gps_wearables" | "strength_conditioning";

export type IntegrationStatus = "not_connected" | "connected";

export interface HealthWorkloadIntegration {
  source: IntegrationSource;
  displayName: string;
  description: string;
  status: IntegrationStatus;
  dataCategories: string[];
  providerExamples: string[];
}

// Shown verbatim. Reviewed so the surface never implies a medical device, a
// diagnosis, or an injury prediction.
export const HEALTH_WORKLOAD_DISCLAIMER =
  "Training-load and wellness context for sports-performance staff only. " +
  "This surface is not a medical device and does not diagnose injuries or " +
  "predict injury risk. It supports staff judgement; it does not replace it.";

export const HEALTH_WORKLOAD_INTEGRATIONS: readonly HealthWorkloadIntegration[] = [
  {
    source: "wellness",
    displayName: "Wellness self-report",
    description:
      "Athlete-submitted daily wellness check-ins. Self-reported context only — never a clinical assessment.",
    status: "not_connected",
    dataCategories: ["Self-reported soreness", "Self-reported sleep", "Self-reported energy"],
    providerExamples: ["Team wellness questionnaire", "Athlete check-in app"],
  },
  {
    source: "gps_wearables",
    displayName: "GPS / wearables",
    description:
      "Practice and game movement load from GPS units and wearables — distance, speed bands, and accelerations as training-load context.",
    status: "not_connected",
    dataCategories: ["Total distance", "High-speed distance", "Accelerations", "Player load"],
    providerExamples: ["GPS tracking vest", "Wrist / chest wearable"],
  },
  {
    source: "strength_conditioning",
    displayName: "Strength & conditioning",
    description:
      "Weight-room and conditioning volume logged by S&C staff — session load and tonnage as planning context.",
    status: "not_connected",
    dataCategories: ["Session volume", "Tonnage", "Session RPE"],
    providerExamples: ["S&C session log", "Weight-room tracking sheet"],
  },
];
