export type PageKey =
  | "dashboard"
  | "library"
  | "video-and-plays"
  | "players"
  | "analytics"
  | "self-scout"
  | "opponent-scout"
  | "player-development"
  | "health-workload"
  | "reports"
  | "clips-highlights"
  | "alerts"
  | "clip-review"
  | "settings";

// Backend-aligned enums (ADR 0001). These describe API payloads, not the
// existing UI filter literals in app-state.tsx — the ADR explicitly defers
// the UI-side `"special"` → `"special_teams"` rename.
export type SessionKind = "practice" | "scrimmage" | "game";
export type SourceType = "drone" | "uploaded_clip";
export type OurPossession = "offense" | "defense" | "special_teams";
export type ApiSideOfBall = "offense" | "defense" | "special_teams";

export interface ApiVideo {
  id: string;
  filename: string;
  status: string;
  duration_seconds?: number | null;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  created_at: string;
  recorded_at?: string | null;
  session_kind?: SessionKind | null;
  source_type?: SourceType | null;
  opponent_team?: string | null;
  practice_session_id?: string | null;
  our_possession?: OurPossession | null;
}

export interface ApiClip {
  id: string;
  video_id: string;
  start_time: number;
  end_time: number;
  play_number?: number | null;
  confidence?: number | null;
  is_reviewed?: boolean;
  storage_uri?: string | null;
  label_data?: Record<string, unknown> | null;
  boundary_source?: string | null;
  boundary_confidence?: number | null;
  session_kind?: SessionKind | null;
  our_possession?: OurPossession | null;
  side_of_ball?: ApiSideOfBall | null;
  created_at: string;
}

export interface ApiPracticeSessionGroup {
  practice_session_id?: string | null;
  session_date?: string | null;
  session_kind?: SessionKind | null;
  opponent_team?: string | null;
  video_count: number;
  first_recorded_at?: string | null;
  last_recorded_at?: string | null;
}

export interface ApiJob {
  id: string;
  job_type: string;
  status: string;
  priority: number;
  pipeline_mode?: string | null;
  is_same_session?: boolean;
  error_stage?: string | null;
  error_message?: string | null;
  nightly_followup_job_id?: string | null;
  created_at: string;
}

export interface SelfScoutResponse {
  formation_tendencies: TendencyEntry[];
  motion_tendencies: {
    with_motion: MotionSplit;
    without_motion: MotionSplit;
  };
  field_zone_tendencies: TendencyEntry[];
  personnel_tendencies: TendencyEntry[];
  down_distance_tendencies: Array<TendencyEntry & { down: number; distance_bucket: string }>;
  formation_concept_families: Record<string, ConceptFamilyEntry[]>;
  pre_snap_tells: ExposureAlert[];
  alerts: TendencyAlert[];
  clip_count: number;
}

export interface TendencyEntry {
  grouping_key: string;
  total_plays: number;
  run_count: number;
  pass_count: number;
  run_rate: number;
  pass_rate: number;
  evidence_clip_ids: string[];
  low_sample: boolean;
}

export interface MotionSplit {
  total: number;
  run_count: number;
  pass_count: number;
  run_rate: number;
  pass_rate: number;
}

export interface ConceptFamilyEntry {
  formation: string;
  concept_family: string;
  total_plays: number;
  rate: number;
  evidence_clip_ids: string[];
  low_sample: boolean;
}

export interface ExposureAlert {
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

export interface TendencyAlert {
  alert_type: string;
  message: string;
  severity: string;
  grouping_key: string;
  run_rate: number;
  pass_rate: number;
}

export interface FootballData {
  videos: ApiVideo[];
  jobs: ApiJob[];
  selfScout: SelfScoutResponse;
  players: PlayerSummary[];
  plays: PlaySummary[];
  clips: ClipSummary[];
  health: HealthSummary[];
  alerts: AlertSummary[];
}

export interface PlayerSummary {
  id: string;
  jersey: string;
  name: string;
  position: string;
  group: string;
  maxSpeed: number;
  distance: number;
  separation: number;
  confidence: number;
  trend: number[];
}

export interface PlaySummary {
  number: number;
  formation: string;
  personnel: string;
  concept: string;
  result: string;
  yards: number;
  confidence: number;
}

export interface ClipSummary {
  id: string;
  title: string;
  subtitle: string;
  duration: string;
  tag: string;
}

export interface HealthSummary {
  player: string;
  load: string;
  status: "Low" | "Med" | "High";
}

export interface AlertSummary {
  title: string;
  detail: string;
  severity: "good" | "warning" | "danger" | "info";
}
