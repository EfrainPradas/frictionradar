import { apiClient } from './apiClient';

export interface StepResult {
  status: 'ok' | 'error';
  elapsed_s: number;
  result?: Record<string, unknown>;
  error?: string;
}

export interface NightlyRunSummary {
  run_id: string;
  started_at: string | null;
  total_elapsed_s: number;
  steps: Record<string, StepResult>;
  errors: { step: string; error: string }[];
  error_count: number;
}

export interface CronJobRun {
  start_time: string | null;
  end_time: string | null;
  status: string;
  return_message: string | null;
}

export interface CronJob {
  job_name: string;
  schedule: string;
  command: string;
  active: boolean;
  last_runs: CronJobRun[];
}

export interface PipelineStatus {
  nightly_run: NightlyRunSummary | null;
  nightly_running: boolean;
  collection_stats: {
    total_runs_24h: number;
    completed_24h: number;
    failed_24h: number;
    running_now: number;
  };
  signal_freshness: {
    total_companies: number;
    signal_last_24h: number;
    signal_last_7d: number;
    signal_older: number;
  };
  vip_stats: {
    active_opportunities: number;
    last_generated_at: string | null;
  };
  cron_jobs: CronJob[];
}

export const operationsService = {
  getStatus: () =>
    apiClient.get<PipelineStatus>('/operations/pipeline/status').then(r => r.data),

  triggerRun: () =>
    apiClient.post<{ status: string; run_id: string }>('/operations/pipeline/trigger').then(r => r.data),
};