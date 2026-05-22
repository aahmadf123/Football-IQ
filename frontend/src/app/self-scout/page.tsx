"use client";

import { useMemo, useState } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

interface TendencyEntry {
  grouping_key: string;
  total_plays: number;
  run_count: number;
  pass_count: number;
  run_rate: number;
  pass_rate: number;
  evidence_clip_ids: string[];
  low_sample: boolean;
}

interface MotionTendency {
  total: number;
  run_count: number;
  pass_count: number;
  run_rate: number;
  pass_rate: number;
}

interface DownDistanceTendency {
  down: number;
  distance_bucket: string;
  total_plays: number;
  run_count: number;
  pass_count: number;
  run_rate: number;
  pass_rate: number;
  evidence_clip_ids: string[];
  low_sample: boolean;
}

interface ConceptFamilyEntry {
  formation: string;
  concept_family: string;
  total_plays: number;
  rate: number;
  evidence_clip_ids: string[];
  low_sample: boolean;
}

interface ExposureAlert {
  grouping_key: string;
  formation: string;
  motion_state: string;
  total_plays: number;
  lean: string;
  severity: string;
  run_rate: number;
  pass_rate: number;
  evidence_clip_ids: string[];
  low_sample: boolean;
  message: string;
}

interface TendencyAlert {
  alert_type: string;
  message: string;
  severity: string;
  grouping_key: string;
  run_rate: number;
  pass_rate: number;
}

// ── Sample Data ──────────────────────────────────────────────────────────────

const sampleFormationTendencies: TendencyEntry[] = [
  {
    grouping_key: "shotgun",
    total_plays: 48,
    run_count: 14,
    pass_count: 34,
    run_rate: 0.292,
    pass_rate: 0.708,
    evidence_clip_ids: ["c1", "c2", "c3"],
    low_sample: false,
  },
  {
    grouping_key: "pistol",
    total_plays: 32,
    run_count: 26,
    pass_count: 6,
    run_rate: 0.813,
    pass_rate: 0.188,
    evidence_clip_ids: ["c4", "c5", "c6"],
    low_sample: false,
  },
  {
    grouping_key: "trips",
    total_plays: 21,
    run_count: 4,
    pass_count: 17,
    run_rate: 0.19,
    pass_rate: 0.81,
    evidence_clip_ids: ["c7", "c8"],
    low_sample: false,
  },
  {
    grouping_key: "empty",
    total_plays: 12,
    run_count: 1,
    pass_count: 11,
    run_rate: 0.083,
    pass_rate: 0.917,
    evidence_clip_ids: ["c9"],
    low_sample: false,
  },
  {
    grouping_key: "under_center",
    total_plays: 8,
    run_count: 7,
    pass_count: 1,
    run_rate: 0.875,
    pass_rate: 0.125,
    evidence_clip_ids: ["c10"],
    low_sample: true,
  },
];

const sampleMotionTendencies = {
  with_motion: {
    total: 34,
    run_count: 22,
    pass_count: 12,
    run_rate: 0.647,
    pass_rate: 0.353,
  } as MotionTendency,
  without_motion: {
    total: 87,
    run_count: 30,
    pass_count: 57,
    run_rate: 0.345,
    pass_rate: 0.655,
  } as MotionTendency,
};

const sampleFieldZoneTendencies: TendencyEntry[] = [
  {
    grouping_key: "mid_field",
    total_plays: 61,
    run_count: 27,
    pass_count: 34,
    run_rate: 0.443,
    pass_rate: 0.557,
    evidence_clip_ids: [],
    low_sample: false,
  },
  {
    grouping_key: "red_zone",
    total_plays: 28,
    run_count: 20,
    pass_count: 8,
    run_rate: 0.714,
    pass_rate: 0.286,
    evidence_clip_ids: [],
    low_sample: false,
  },
  {
    grouping_key: "backed_up",
    total_plays: 14,
    run_count: 10,
    pass_count: 4,
    run_rate: 0.714,
    pass_rate: 0.286,
    evidence_clip_ids: [],
    low_sample: false,
  },
];

const samplePersonnelTendencies: TendencyEntry[] = [
  {
    grouping_key: "11",
    total_plays: 55,
    run_count: 18,
    pass_count: 37,
    run_rate: 0.327,
    pass_rate: 0.673,
    evidence_clip_ids: [],
    low_sample: false,
  },
  {
    grouping_key: "12",
    total_plays: 28,
    run_count: 21,
    pass_count: 7,
    run_rate: 0.75,
    pass_rate: 0.25,
    evidence_clip_ids: [],
    low_sample: false,
  },
  {
    grouping_key: "21",
    total_plays: 16,
    run_count: 13,
    pass_count: 3,
    run_rate: 0.813,
    pass_rate: 0.188,
    evidence_clip_ids: [],
    low_sample: false,
  },
];

const sampleDownDistanceTendencies: DownDistanceTendency[] = [
  {
    down: 1,
    distance_bucket: "long",
    total_plays: 38,
    run_count: 22,
    pass_count: 16,
    run_rate: 0.579,
    pass_rate: 0.421,
    evidence_clip_ids: [],
    low_sample: false,
  },
  {
    down: 2,
    distance_bucket: "medium",
    total_plays: 22,
    run_count: 8,
    pass_count: 14,
    run_rate: 0.364,
    pass_rate: 0.636,
    evidence_clip_ids: [],
    low_sample: false,
  },
  {
    down: 2,
    distance_bucket: "long",
    total_plays: 14,
    run_count: 3,
    pass_count: 11,
    run_rate: 0.214,
    pass_rate: 0.786,
    evidence_clip_ids: [],
    low_sample: false,
  },
  {
    down: 3,
    distance_bucket: "short",
    total_plays: 12,
    run_count: 6,
    pass_count: 6,
    run_rate: 0.5,
    pass_rate: 0.5,
    evidence_clip_ids: [],
    low_sample: false,
  },
  {
    down: 3,
    distance_bucket: "long",
    total_plays: 18,
    run_count: 2,
    pass_count: 16,
    run_rate: 0.111,
    pass_rate: 0.889,
    evidence_clip_ids: [],
    low_sample: false,
  },
];

const sampleConceptFamilies: Record<string, ConceptFamilyEntry[]> = {
  shotgun: [
    {
      formation: "shotgun",
      concept_family: "pass_concept",
      total_plays: 28,
      rate: 0.583,
      evidence_clip_ids: [],
      low_sample: false,
    },
    {
      formation: "shotgun",
      concept_family: "inside_zone",
      total_plays: 10,
      rate: 0.208,
      evidence_clip_ids: [],
      low_sample: false,
    },
    {
      formation: "shotgun",
      concept_family: "outside_zone",
      total_plays: 6,
      rate: 0.125,
      evidence_clip_ids: [],
      low_sample: true,
    },
    {
      formation: "shotgun",
      concept_family: "gap",
      total_plays: 4,
      rate: 0.083,
      evidence_clip_ids: [],
      low_sample: true,
    },
  ],
  pistol: [
    {
      formation: "pistol",
      concept_family: "inside_zone",
      total_plays: 14,
      rate: 0.438,
      evidence_clip_ids: [],
      low_sample: false,
    },
    {
      formation: "pistol",
      concept_family: "gap",
      total_plays: 10,
      rate: 0.313,
      evidence_clip_ids: [],
      low_sample: false,
    },
    {
      formation: "pistol",
      concept_family: "pass_concept",
      total_plays: 5,
      rate: 0.156,
      evidence_clip_ids: [],
      low_sample: true,
    },
    {
      formation: "pistol",
      concept_family: "outside_zone",
      total_plays: 3,
      rate: 0.094,
      evidence_clip_ids: [],
      low_sample: true,
    },
  ],
};

const samplePreSnapTells: ExposureAlert[] = [
  {
    grouping_key: "pistol|without_motion",
    formation: "pistol",
    motion_state: "without_motion",
    total_plays: 24,
    lean: "run",
    severity: "high",
    run_rate: 0.917,
    pass_rate: 0.083,
    evidence_clip_ids: ["c4", "c5"],
    low_sample: false,
    message: "Pre-snap tell from pistol without motion: 92% run (24 plays)",
  },
  {
    grouping_key: "empty|without_motion",
    formation: "empty",
    motion_state: "without_motion",
    total_plays: 12,
    lean: "pass",
    severity: "high",
    run_rate: 0.083,
    pass_rate: 0.917,
    evidence_clip_ids: ["c9"],
    low_sample: false,
    message: "Pre-snap tell from empty without motion: 92% pass (12 plays)",
  },
  {
    grouping_key: "trips|with_motion",
    formation: "trips",
    motion_state: "with_motion",
    total_plays: 8,
    lean: "pass",
    severity: "medium",
    run_rate: 0.125,
    pass_rate: 0.875,
    evidence_clip_ids: [],
    low_sample: true,
    message: "Pre-snap tell from trips with motion: 88% pass (8 plays)",
  },
];

const sampleAlerts: TendencyAlert[] = [
  {
    alert_type: "formation_tendency",
    message: "High run tendency from pistol: 81% (32 plays)",
    severity: "medium",
    grouping_key: "pistol",
    run_rate: 0.813,
    pass_rate: 0.188,
  },
  {
    alert_type: "formation_tendency",
    message: "High pass tendency from empty: 92% (12 plays)",
    severity: "high",
    grouping_key: "empty",
    run_rate: 0.083,
    pass_rate: 0.917,
  },
  {
    alert_type: "formation_tendency",
    message: "High pass tendency from trips: 81% (21 plays)",
    severity: "medium",
    grouping_key: "trips",
    run_rate: 0.19,
    pass_rate: 0.81,
  },
  {
    alert_type: "personnel_tendency",
    message: "High run tendency from 21: 81%",
    severity: "medium",
    grouping_key: "21",
    run_rate: 0.813,
    pass_rate: 0.188,
  },
  {
    alert_type: "field_zone_tendency",
    message: "High run tendency in red_zone: 71%",
    severity: "medium",
    grouping_key: "red_zone",
    run_rate: 0.714,
    pass_rate: 0.286,
  },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function pct(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function severityColor(severity: string): string {
  if (severity === "high") return "#dc2626";
  if (severity === "medium") return "#f59e0b";
  return "#6b7280";
}

function barStyle(rate: number, color: string): React.CSSProperties {
  return {
    width: `${rate * 100}%`,
    backgroundColor: color,
    height: "14px",
    borderRadius: "3px",
    transition: "width 0.3s ease",
  };
}

type TabKey =
  | "formation"
  | "motion"
  | "field_zone"
  | "personnel"
  | "down_distance"
  | "concept_family"
  | "exposure";

const TAB_LABELS: Record<TabKey, string> = {
  formation: "Formation",
  motion: "Motion",
  field_zone: "Field Zone",
  personnel: "Personnel",
  down_distance: "Down & Distance",
  concept_family: "Concept Family",
  exposure: "Exposure Alerts",
};

// ── Components ───────────────────────────────────────────────────────────────

function RunPassBar({ runRate, passRate }: { runRate: number; passRate: number }) {
  return (
    <div style={{ display: "flex", gap: "2px", width: "100%" }}>
      <div style={barStyle(runRate, "#3b82f6")} title={`Run: ${pct(runRate)}`} />
      <div style={barStyle(passRate, "#f97316")} title={`Pass: ${pct(passRate)}`} />
    </div>
  );
}

function LowSampleBadge() {
  return (
    <span
      style={{
        fontSize: "10px",
        color: "#f59e0b",
        border: "1px solid #f59e0b",
        borderRadius: "3px",
        padding: "1px 4px",
        marginLeft: "6px",
      }}
    >
      low-N
    </span>
  );
}

function FormationTable({ data }: { data: TendencyEntry[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px" }}>
      <thead>
        <tr style={{ borderBottom: "2px solid #374151", textAlign: "left" }}>
          <th style={{ padding: "8px" }}>Formation</th>
          <th style={{ padding: "8px", textAlign: "center" }}>Plays</th>
          <th style={{ padding: "8px", textAlign: "center" }}>Run</th>
          <th style={{ padding: "8px", textAlign: "center" }}>Pass</th>
          <th style={{ padding: "8px", width: "30%" }}>Run / Pass Split</th>
        </tr>
      </thead>
      <tbody>
        {data.map((entry) => (
          <tr key={entry.grouping_key} style={{ borderBottom: "1px solid #1f2937" }}>
            <td style={{ padding: "8px", fontWeight: 600 }}>
              {entry.grouping_key}
              {entry.low_sample && <LowSampleBadge />}
            </td>
            <td style={{ padding: "8px", textAlign: "center" }}>{entry.total_plays}</td>
            <td style={{ padding: "8px", textAlign: "center", color: "#3b82f6" }}>
              {pct(entry.run_rate)}
            </td>
            <td style={{ padding: "8px", textAlign: "center", color: "#f97316" }}>
              {pct(entry.pass_rate)}
            </td>
            <td style={{ padding: "8px" }}>
              <RunPassBar runRate={entry.run_rate} passRate={entry.pass_rate} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MotionPanel({
  data,
}: {
  data: { with_motion: MotionTendency; without_motion: MotionTendency };
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
      {(["with_motion", "without_motion"] as const).map((key) => {
        const m = data[key];
        const label = key === "with_motion" ? "With Motion" : "Without Motion";
        return (
          <div
            key={key}
            style={{
              border: "1px solid #374151",
              borderRadius: "8px",
              padding: "16px",
            }}
          >
            <h4 style={{ margin: "0 0 8px 0", fontWeight: 600 }}>{label}</h4>
            <p style={{ margin: "4px 0", fontSize: "13px", color: "#9ca3af" }}>
              {m.total} plays
            </p>
            <div style={{ display: "flex", gap: "24px", margin: "8px 0" }}>
              <span style={{ color: "#3b82f6" }}>Run: {pct(m.run_rate)}</span>
              <span style={{ color: "#f97316" }}>Pass: {pct(m.pass_rate)}</span>
            </div>
            <RunPassBar runRate={m.run_rate} passRate={m.pass_rate} />
          </div>
        );
      })}
    </div>
  );
}

function DownDistanceTable({ data }: { data: DownDistanceTendency[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px" }}>
      <thead>
        <tr style={{ borderBottom: "2px solid #374151", textAlign: "left" }}>
          <th style={{ padding: "8px" }}>Down</th>
          <th style={{ padding: "8px" }}>Distance</th>
          <th style={{ padding: "8px", textAlign: "center" }}>Plays</th>
          <th style={{ padding: "8px", textAlign: "center" }}>Run</th>
          <th style={{ padding: "8px", textAlign: "center" }}>Pass</th>
          <th style={{ padding: "8px", width: "30%" }}>Run / Pass Split</th>
        </tr>
      </thead>
      <tbody>
        {data.map((entry) => (
          <tr
            key={`${entry.down}-${entry.distance_bucket}`}
            style={{ borderBottom: "1px solid #1f2937" }}
          >
            <td style={{ padding: "8px", fontWeight: 600 }}>{entry.down}</td>
            <td style={{ padding: "8px", textTransform: "capitalize" }}>
              {entry.distance_bucket}
              {entry.low_sample && <LowSampleBadge />}
            </td>
            <td style={{ padding: "8px", textAlign: "center" }}>{entry.total_plays}</td>
            <td style={{ padding: "8px", textAlign: "center", color: "#3b82f6" }}>
              {pct(entry.run_rate)}
            </td>
            <td style={{ padding: "8px", textAlign: "center", color: "#f97316" }}>
              {pct(entry.pass_rate)}
            </td>
            <td style={{ padding: "8px" }}>
              <RunPassBar runRate={entry.run_rate} passRate={entry.pass_rate} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ConceptFamilyPanel({
  data,
}: {
  data: Record<string, ConceptFamilyEntry[]>;
}) {
  const formations = Object.keys(data);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {formations.map((formation) => (
        <div
          key={formation}
          style={{
            border: "1px solid #374151",
            borderRadius: "8px",
            padding: "16px",
          }}
        >
          <h4 style={{ margin: "0 0 8px 0", fontWeight: 600, textTransform: "capitalize" }}>
            {formation}
          </h4>
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            {data[formation].map((entry) => (
              <div
                key={entry.concept_family}
                style={{
                  flex: "1 1 140px",
                  backgroundColor: "#1f2937",
                  borderRadius: "6px",
                  padding: "10px",
                  textAlign: "center",
                  minWidth: "120px",
                }}
              >
                <div
                  style={{
                    fontSize: "12px",
                    color: "#9ca3af",
                    marginBottom: "4px",
                    textTransform: "capitalize",
                  }}
                >
                  {entry.concept_family.replace("_", " ")}
                </div>
                <div style={{ fontSize: "22px", fontWeight: 700 }}>{pct(entry.rate)}</div>
                <div style={{ fontSize: "11px", color: "#6b7280" }}>
                  {entry.total_plays} plays
                  {entry.low_sample && <LowSampleBadge />}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ExposurePanel({ data }: { data: ExposureAlert[] }) {
  if (data.length === 0)
    return <p style={{ color: "#6b7280" }}>No pre-snap tells detected.</p>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {data.map((alert) => (
        <div
          key={alert.grouping_key}
          style={{
            border: `1px solid ${severityColor(alert.severity)}`,
            borderLeft: `4px solid ${severityColor(alert.severity)}`,
            borderRadius: "6px",
            padding: "12px 16px",
            backgroundColor: "#111827",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 600 }}>{alert.message}</span>
            <span
              style={{
                fontSize: "11px",
                textTransform: "uppercase",
                color: severityColor(alert.severity),
                fontWeight: 700,
              }}
            >
              {alert.severity}
              {alert.low_sample && <LowSampleBadge />}
            </span>
          </div>
          <div style={{ marginTop: "6px", fontSize: "12px", color: "#9ca3af" }}>
            {alert.total_plays} plays — {pct(alert.run_rate)} run / {pct(alert.pass_rate)} pass
          </div>
          <RunPassBar runRate={alert.run_rate} passRate={alert.pass_rate} />
        </div>
      ))}
    </div>
  );
}

function AlertsPanel({ data }: { data: TendencyAlert[] }) {
  if (data.length === 0) return <p style={{ color: "#6b7280" }}>No tendency alerts.</p>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {data.map((alert, idx) => (
        <div
          key={`${alert.grouping_key}-${alert.alert_type}-${idx}`}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "8px 12px",
            borderRadius: "6px",
            backgroundColor: "#1f2937",
            borderLeft: `3px solid ${severityColor(alert.severity)}`,
          }}
        >
          <span style={{ fontSize: "13px" }}>{alert.message}</span>
          <span
            style={{
              fontSize: "11px",
              textTransform: "uppercase",
              color: severityColor(alert.severity),
              fontWeight: 700,
            }}
          >
            {alert.severity}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SelfScoutDashboard() {
  const [activeTab, setActiveTab] = useState<TabKey>("formation");
  const [viewMode, setViewMode] = useState<"self" | "opponent">("self");

  const tabKeys = useMemo(() => Object.keys(TAB_LABELS) as TabKey[], []);

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "#0a0a0a",
        color: "#e5e7eb",
        padding: "32px 48px",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <h1 style={{ margin: 0, fontSize: "28px", fontWeight: 700 }}>
          🏈 Self-Scout Exposure Dashboard
        </h1>
        <p style={{ margin: "6px 0 0", color: "#9ca3af", fontSize: "14px" }}>
          Identify what opponents would see in Toledo&apos;s pre-snap tendencies. Break
          predictable patterns before they&apos;re exploited.
        </p>
      </div>

      {/* Toggle: Self-Scout vs. Opponent */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
        {(["self", "opponent"] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => setViewMode(mode)}
            style={{
              padding: "6px 16px",
              borderRadius: "6px",
              border: viewMode === mode ? "2px solid #3b82f6" : "1px solid #374151",
              backgroundColor: viewMode === mode ? "#1e3a5f" : "transparent",
              color: viewMode === mode ? "#93c5fd" : "#9ca3af",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "13px",
              textTransform: "capitalize",
            }}
          >
            {mode === "self" ? "Self-Scout" : "Opponent Scout"}
          </button>
        ))}
      </div>

      {/* Alerts Summary */}
      {sampleAlerts.length > 0 && (
        <div
          style={{
            marginBottom: "24px",
            padding: "16px",
            border: "1px solid #374151",
            borderRadius: "8px",
            backgroundColor: "#111827",
          }}
        >
          <h3 style={{ margin: "0 0 10px 0", fontSize: "16px", fontWeight: 600 }}>
            ⚠️ Tendency Alerts ({sampleAlerts.length})
          </h3>
          <AlertsPanel data={sampleAlerts} />
        </div>
      )}

      {/* Tab Navigation */}
      <div
        style={{
          display: "flex",
          gap: "4px",
          borderBottom: "1px solid #374151",
          marginBottom: "20px",
        }}
      >
        {tabKeys.map((key) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: "8px 16px",
              borderRadius: "6px 6px 0 0",
              border: "none",
              backgroundColor: activeTab === key ? "#1f2937" : "transparent",
              color: activeTab === key ? "#f9fafb" : "#6b7280",
              cursor: "pointer",
              fontWeight: activeTab === key ? 600 : 400,
              fontSize: "13px",
              borderBottom: activeTab === key ? "2px solid #3b82f6" : "2px solid transparent",
            }}
          >
            {TAB_LABELS[key]}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div
        style={{
          border: "1px solid #374151",
          borderRadius: "8px",
          padding: "20px",
          backgroundColor: "#111827",
        }}
      >
        {activeTab === "formation" && (
          <>
            <h3 style={{ margin: "0 0 12px 0" }}>Formation → Run / Pass Tendencies</h3>
            <div
              style={{
                display: "flex",
                gap: "16px",
                marginBottom: "12px",
                fontSize: "12px",
                color: "#9ca3af",
              }}
            >
              <span>
                <span style={{ color: "#3b82f6" }}>■</span> Run
              </span>
              <span>
                <span style={{ color: "#f97316" }}>■</span> Pass
              </span>
            </div>
            <FormationTable data={sampleFormationTendencies} />
          </>
        )}

        {activeTab === "motion" && (
          <>
            <h3 style={{ margin: "0 0 12px 0" }}>Motion → Run / Pass Split</h3>
            <MotionPanel data={sampleMotionTendencies} />
          </>
        )}

        {activeTab === "field_zone" && (
          <>
            <h3 style={{ margin: "0 0 12px 0" }}>Field Zone Tendencies</h3>
            <FormationTable data={sampleFieldZoneTendencies} />
          </>
        )}

        {activeTab === "personnel" && (
          <>
            <h3 style={{ margin: "0 0 12px 0" }}>Personnel Grouping Tendencies</h3>
            <FormationTable data={samplePersonnelTendencies} />
          </>
        )}

        {activeTab === "down_distance" && (
          <>
            <h3 style={{ margin: "0 0 12px 0" }}>Down & Distance Breakdown</h3>
            <DownDistanceTable data={sampleDownDistanceTendencies} />
          </>
        )}

        {activeTab === "concept_family" && (
          <>
            <h3 style={{ margin: "0 0 12px 0" }}>Concept Family Distribution by Formation</h3>
            <ConceptFamilyPanel data={sampleConceptFamilies} />
          </>
        )}

        {activeTab === "exposure" && (
          <>
            <h3 style={{ margin: "0 0 12px 0" }}>
              Pre-Snap Tell Exposure View (≥80% lean)
            </h3>
            <p style={{ fontSize: "13px", color: "#9ca3af", marginBottom: "12px" }}>
              Formation + motion combos that telegraph play calls. These are what a prepared
              opponent would exploit.
            </p>
            <ExposurePanel data={samplePreSnapTells} />
          </>
        )}
      </div>

      {/* Clip count / meta */}
      <div
        style={{
          marginTop: "16px",
          fontSize: "12px",
          color: "#6b7280",
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>121 clips analyzed · {viewMode === "self" ? "Self-Scout" : "Opponent Scout"}</span>
        <span>
          Data: sample · Season filter and live API integration coming soon
        </span>
      </div>
    </div>
  );
}
