/**
 * Cloudflare Queues helpers — submit jobs to the processing queues.
 */

import type { Env } from "./types.js";

export interface VideoProcessingJob {
  jobId: string;
  videoId: string;
  jobType: string;
  priority: number;
  inputUri: string;
  submittedAt: string;
}

export interface NightlyTrainingExport {
  exportId: string;
  datasetVersion: string;
  triggeredAt: string;
}

export async function enqueueVideoProcessingJob(
  env: Env,
  job: VideoProcessingJob,
): Promise<void> {
  await env.VIDEO_PROCESSING_QUEUE.send(job);
}

export async function enqueueNightlyTrainingExport(
  env: Env,
  payload: NightlyTrainingExport,
): Promise<void> {
  await env.NIGHTLY_TRAINING_QUEUE.send(payload);
}
