import { useState, useEffect, useCallback } from 'react';
import { operationsService, type PipelineStatus, type NightlyRunSummary, type StepResult, type CronJob } from '../../services/operations';

const STEP_LABELS: Record<string, string> = {
  '1_ats_refresh': 'ATS Refresh',
  '2_careers_refresh': 'Careers Refresh',
  '3_signal_extraction': 'Signal Extraction',
  '4_pain_recomputation': 'Pain Recomputation',
  '5_heatmap_regen': 'Heatmap Regeneration',
  '6_candidate_alignment': 'Candidate Alignment',
  '7_vip_regeneration': 'VIP Regeneration',
  '8_snapshot_persistence': 'Snapshot Persistence',
  '9_temporal_tracking': 'Temporal Tracking',
  '10_delta_computation': 'Delta Computation',
};

const POLL_INTERVAL = 5000;

function StatusBadge({ status }: { status: string }) {
  const cls = status === 'ok'
    ? 'bg-emerald-100 text-emerald-700'
    : status === 'error'
    ? 'bg-red-100 text-red-700'
    : status === 'succeeded'
    ? 'bg-emerald-100 text-emerald-700'
    : status === 'running'
    ? 'bg-amber-100 text-amber-700'
    : 'bg-gray-100 text-gray-600';

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${cls}`}>
      {status === 'ok' ? 'OK' : status === 'succeeded' ? 'OK' : status === 'error' ? 'FAIL' : status.toUpperCase()}
    </span>
  );
}

function StepTable({ steps }: { steps: Record<string, StepResult> }) {
  const entries = Object.entries(steps);
  if (entries.length === 0) return <div className="text-[13px] text-fr-ink-mute">No step data available.</div>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-fr-line text-left text-[11px] text-fr-ink-faint uppercase tracking-wider">
            <th className="py-2 pr-4 font-medium">Step</th>
            <th className="py-2 pr-4 font-medium w-20">Status</th>
            <th className="py-2 pr-4 font-medium w-24 text-right">Elapsed</th>
            <th className="py-2 font-medium">Result</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, step]) => (
            <tr key={key} className="border-b border-fr-line/50">
              <td className="py-2 pr-4 text-fr-ink">{STEP_LABELS[key] || key}</td>
              <td className="py-2 pr-4"><StatusBadge status={step.status} /></td>
              <td className="py-2 pr-4 text-right text-fr-ink-mute tabular-nums">{step.elapsed_s?.toFixed(1) ?? '—'}s</td>
              <td className="py-2 text-fr-ink-faint text-[12px] truncate max-w-[300px]">
                {step.error
                  ? <span className="text-red-600">{step.error}</span>
                  : step.result
                  ? JSON.stringify(step.result).slice(0, 80)
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: string }) {
  const cls = accent === 'green' ? 'text-emerald-600' : accent === 'red' ? 'text-red-600' : accent === 'amber' ? 'text-amber-600' : 'text-fr-ink';
  return (
    <div className="rounded-lg border border-fr-line bg-fr-paper p-4 text-center">
      <div className={`text-2xl font-semibold ${cls}`}>{value}</div>
      <div className="text-[11px] text-fr-ink-faint mt-1">{label}</div>
      {sub && <div className="text-[11px] text-fr-ink-mute mt-0.5">{sub}</div>}
    </div>
  );
}

function CronJobsTable({ jobs }: { jobs: CronJob[] }) {
  if (jobs.length === 0) return <div className="text-[13px] text-fr-ink-mute">No cron jobs found.</div>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-fr-line text-left text-[11px] text-fr-ink-faint uppercase tracking-wider">
            <th className="py-2 pr-4 font-medium">Job</th>
            <th className="py-2 pr-4 font-medium">Schedule</th>
            <th className="py-2 pr-4 font-medium w-20">Last Status</th>
            <th className="py-2 font-medium w-40">Last Run</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => {
            const lastRun = job.last_runs?.[0];
            return (
              <tr key={job.job_name} className="border-b border-fr-line/50">
                <td className="py-2 pr-4 text-fr-ink font-mono text-[12px]">{job.job_name}</td>
                <td className="py-2 pr-4 text-fr-ink-mute font-mono text-[12px]">{job.schedule}</td>
                <td className="py-2 pr-4">{lastRun ? <StatusBadge status={lastRun.status} /> : <span className="text-fr-ink-faint">—</span>}</td>
                <td className="py-2 text-fr-ink-faint text-[12px]">{lastRun?.start_time ? new Date(lastRun.start_time).toLocaleString() : '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function formatElapsed(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`;
  const mins = Math.floor(totalSeconds / 60);
  const secs = Math.round(totalSeconds % 60);
  return `${mins}m ${secs}s`;
}

export function PipelineOperationsPage() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await operationsService.getStatus();
      setStatus(data);
      setError(null);
      return data.nightly_running;
    } catch (err: any) {
      setError(err.message || 'Failed to fetch pipeline status');
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // Poll while nightly is running
  useEffect(() => {
    if (!status?.nightly_running) return;
    const id = setInterval(async () => {
      const stillRunning = await fetchStatus();
      if (!stillRunning) clearInterval(id);
    }, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [status?.nightly_running, fetchStatus]);

  const handleTrigger = async () => {
    setTriggering(true);
    setError(null);
    try {
      await operationsService.triggerRun();
      // Immediately re-fetch to show "running" state
      await fetchStatus();
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message || 'Failed to trigger pipeline';
      setError(detail);
    } finally {
      setTriggering(false);
    }
  };

  const isRunning = status?.nightly_running || triggering;

  return (
    <div className="p-7 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint mb-1">System · Operations</div>
          <h1 className="text-[22px] font-semibold text-fr-ink leading-tight">Pipeline Operations</h1>
          <p className="text-[13px] text-fr-ink-mute mt-1.5 max-w-md leading-relaxed">
            Monitor nightly collection, scoring, and VIP generation. View run history and trigger manual executions.
          </p>
        </div>
        <button
          type="button"
          onClick={handleTrigger}
          disabled={isRunning}
          className="shrink-0 text-[12px] font-semibold text-fr-paper bg-fr-ink rounded-md px-3.5 py-2 hover:bg-fr-ink-soft transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isRunning ? 'Running...' : 'Run Nightly Pipeline'}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-[13px] text-red-700">
          {error}
        </div>
      )}

      {loading && (
        <div className="rounded-lg border border-fr-line bg-fr-paper p-8 text-center">
          <div className="text-sm text-fr-ink-mute">Loading pipeline status...</div>
        </div>
      )}

      {!loading && status && (
        <>
          {/* Running banner */}
          {status.nightly_running && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 flex items-center gap-3">
              <div className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
              <div>
                <div className="text-[13px] font-semibold text-amber-800">Pipeline is running</div>
                <div className="text-[12px] text-amber-600">This page will update automatically when complete.</div>
              </div>
            </div>
          )}

          {/* Collection Stats */}
          <div className="grid grid-cols-4 gap-3">
            <StatCard label="Completed (24h)" value={status.collection_stats.completed_24h} accent="green" />
            <StatCard label="Failed (24h)" value={status.collection_stats.failed_24h} accent="red" />
            <StatCard label="Running Now" value={status.collection_stats.running_now} accent="amber" />
            <StatCard
              label="Signal Freshness"
              value={`${Math.round((status.signal_freshness.signal_last_24h / Math.max(status.signal_freshness.total_companies, 1)) * 100)}%`}
              sub={`${status.signal_freshness.signal_last_24h} of ${status.signal_freshness.total_companies} companies`}
            />
          </div>

          {/* Nightly Run Status */}
          <div className="rounded-lg border border-fr-line bg-fr-paper">
            <div className="px-4 py-3 border-b border-fr-line flex items-center justify-between">
              <div>
                <div className="text-[13px] font-semibold text-fr-ink">Last Nightly Run</div>
                {status.nightly_run && (
                  <div className="text-[11px] text-fr-ink-faint mt-0.5">
                    {status.nightly_run.run_id} · {status.nightly_run.started_at ? new Date(status.nightly_run.started_at).toLocaleString() : '—'} · {formatElapsed(status.nightly_run.total_elapsed_s)}
                    {status.nightly_run.error_count > 0 && (
                      <span className="text-red-600 ml-2">{status.nightly_run.error_count} error{status.nightly_run.error_count > 1 ? 's' : ''}</span>
                    )}
                  </div>
                )}
              </div>
              {status.nightly_run && (
                <StatusBadge status={status.nightly_run.error_count > 0 ? 'error' : 'ok'} />
              )}
            </div>
            <div className="px-4 py-3">
              {status.nightly_run ? (
                <StepTable steps={status.nightly_run.steps} />
              ) : (
                <div className="text-[13px] text-fr-ink-mute py-4 text-center">No nightly run recorded yet. Trigger one to see results.</div>
              )}
            </div>
          </div>

          {/* VIP Stats + Cron Jobs */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-fr-line bg-fr-paper p-4">
              <div className="text-[13px] font-semibold text-fr-ink mb-3">VIP Opportunities</div>
              <div className="flex gap-4">
                <StatCard label="Active" value={status.vip_stats.active_opportunities} />
                <StatCard
                  label="Last Generated"
                  value={status.vip_stats.last_generated_at ? new Date(status.vip_stats.last_generated_at).toLocaleDateString() : '—'}
                />
              </div>
            </div>

            <div className="rounded-lg border border-fr-line bg-fr-paper p-4">
              <div className="text-[13px] font-semibold text-fr-ink mb-3">Cron Jobs</div>
              <CronJobsTable jobs={status.cron_jobs} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}