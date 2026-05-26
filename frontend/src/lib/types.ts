export type PageKey =
  | "dashboard"
  | "video-and-plays"
  | "players"
  | "analytics"
  | "self-scout"
  | "opponent-scout"
  | "player-development"
  | "health-workload"
  | "reports"
  | "clips-highlights"
  | "settings";

export interface ApiVideo {
  id: string;
  filename: string;
  status: string;
  duration_seconds?: number | null;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  created_at: string;
}

export interface ApiJob {
  id: string;
  job_type: string;
  status: string;
  priority: number;
  error_stage?: string | null;
  error_message?: string | null;
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
