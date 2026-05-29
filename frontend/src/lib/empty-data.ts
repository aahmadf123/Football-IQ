import type { FootballData, SelfScoutResponse } from "./types";

const emptySelfScout: SelfScoutResponse = {
  formation_tendencies: [],
  motion_tendencies: {
    with_motion: { total: 0, run_count: 0, pass_count: 0, run_rate: 0, pass_rate: 0 },
    without_motion: { total: 0, run_count: 0, pass_count: 0, run_rate: 0, pass_rate: 0 },
  },
  field_zone_tendencies: [],
  personnel_tendencies: [],
  down_distance_tendencies: [],
  formation_concept_families: {},
  pre_snap_tells: [],
  alerts: [],
  clip_count: 0,
};

export const emptyFootballData: FootballData = {
  videos: [],
  jobs: [],
  selfScout: emptySelfScout,
  players: [],
  plays: [],
  clips: [],
  health: [],
  alerts: [],
};
