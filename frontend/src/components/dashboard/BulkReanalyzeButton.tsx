import { useCallback, useEffect, useRef, useState } from 'react';
import { analysisService } from '../../services/analysis';
import type { Company } from '../../types/company';

interface Props {
  companies: Company[];
  analyzedIds?: Set<string>;
  onDone?: () => void;
  concurrency?: number;
}

type RowStatus = 'pending' | 'running' | 'ok' | 'error';

interface RunState {
  total: number;
  done: number;
  ok: number;
  errors: number;
  current: string[];
  failedNames: string[];
  startedAt: number;
}

const INITIAL: RunState = {
  total: 0,
  done: 0,
  ok: 0,
  errors: 0,
  current: [],
  failedNames: [],
  startedAt: 0,
};

export function BulkReanalyzeButton({ companies, analyzedIds, onDone, concurrency = 5 }: Props) {
  const [running, setRunning] = useState(false);
  const [state, setState] = useState<RunState>(INITIAL);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [exporting, setExporting] = useState(false);
  const cancelRef = useRef(false);

  // Live stopwatch
  useEffect(() => {
    if (!running || !state.startedAt) {
      setElapsed(0);
      return;
    }
    const id = setInterval(
      () => setElapsed(Math.floor((Date.now() - state.startedAt) / 1000)),
      500,
    );
    return () => clearInterval(id);
  }, [running, state.startedAt]);

  const run = useCallback(async () => {
    if (companies.length === 0) return;
    setConfirmOpen(false);
    setRunning(true);
    cancelRef.current = false;

    const toAnalyze = analyzedIds
      ? companies.filter((c) => !analyzedIds.has(c.id))
      : companies;

    const statuses = new Map<string, RowStatus>();
    toAnalyze.forEach((c) => statuses.set(c.id, 'pending'));

    let next = 0;
    let done = 0;
    let ok = 0;
    let errors = 0;
    const failedNames: string[] = [];
    const current = new Set<string>();

    setState({
      total: toAnalyze.length,
      done: 0,
      ok: 0,
      errors: 0,
      current: [],
      failedNames: [],
      startedAt: Date.now(),
    });

    const worker = async () => {
      while (true) {
        if (cancelRef.current) return;
        const idx = next++;
        if (idx >= toAnalyze.length) return;
        const c = toAnalyze[idx];
        statuses.set(c.id, 'running');
        current.add(c.name);
        setState((s) => ({ ...s, current: Array.from(current) }));
        try {
          await analysisService.recalculateAll(c.id);
          statuses.set(c.id, 'ok');
          ok++;
        } catch {
          statuses.set(c.id, 'error');
          errors++;
          failedNames.push(c.name);
        }
        done++;
        current.delete(c.name);
        setState((s) => ({
          ...s,
          done,
          ok,
          errors,
          current: Array.from(current),
          failedNames: [...failedNames],
        }));
      }
    };

    const workers = Array.from(
      { length: Math.min(concurrency, toAnalyze.length) },
      worker,
    );
    await Promise.all(workers);

    setRunning(false);
    onDone?.();
  }, [companies, analyzedIds, concurrency, onDone]);

  const cancel = useCallback(() => {
    cancelRef.current = true;
  }, []);

  const exportJson = useCallback(async () => {
    setExporting(true);
    try {
      const { apiClient } = await import('../../services/apiClient');
      const response = await apiClient.get('/export-all', { timeout: 600000 });
      const blob = new Blob([JSON.stringify(response.data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `frictionradar_export_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Export failed — check console');
      console.error(e);
    } finally {
      setExporting(false);
    }
  }, []);

  // ── Render: running state ───────────────────────────────────
  if (running) {
    const pct =
      state.total > 0 ? Math.round((state.done / state.total) * 100) : 0;
    const avgPerCompany = state.done > 0 ? elapsed / state.done : 0;
    const remaining = Math.max(0, state.total - state.done);
    const etaSec =
      state.done > 0
        ? Math.ceil((remaining * avgPerCompany) / concurrency)
        : 0;
    const etaMin = Math.ceil(etaSec / 60);

    const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const ss = String(elapsed % 60).padStart(2, '0');

    return (
      <div className="rounded-lg border border-orbital-border bg-[#0b0f12] p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-gray-200">
              Re-analyzing companies…
            </p>
            <p className="text-xs text-gray-500">
              {state.done}/{state.total} done · {state.ok} ok · {state.errors}{' '}
              errors
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-lg font-mono font-bold text-gray-200">
                {mm}:{ss}
              </p>
              {state.done > 0 && (
                <p className="text-[10px] text-gray-600">
                  {avgPerCompany.toFixed(1)}s/co · ETA ~{etaMin}m
                </p>
              )}
            </div>
            <button
              onClick={cancel}
              className="text-xs text-red-400 hover:text-red-300 underline"
            >
              Cancel
            </button>
          </div>
        </div>

        {/* Gauge */}
        <div className="relative h-3 w-full rounded-full bg-white/5 overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-amber-500/60 transition-all duration-500 rounded-full"
            style={{ width: `${pct}%` }}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-[10px] font-bold text-gray-300">{pct}%</span>
          </div>
        </div>

        {state.current.length > 0 && (
          <p className="text-xs text-gray-600 truncate">
            In progress: {state.current.slice(0, 3).join(', ')}
            {state.current.length > 3
              ? ` +${state.current.length - 3}`
              : ''}
          </p>
        )}
      </div>
    );
  }

  // ── Render: confirm dialog ──────────────────────────────────
  if (confirmOpen) {
    const pending = analyzedIds
      ? companies.filter((c) => !analyzedIds.has(c.id)).length
      : companies.length;
    const avgSeconds = 15;
    const etaMin = Math.ceil(
      (pending * avgSeconds) / concurrency / 60,
    );
    return (
      <div className="rounded-lg border border-amber-500/20 bg-amber-950/20 p-4 space-y-3">
        <p className="text-sm text-amber-200">
          {analyzedIds ? (
            <>Will analyze <strong>{pending}</strong> pending companies ({companies.length - pending} already done). </>
          ) : (
            <>Will re-analyze <strong>{pending}</strong> companies. </>
          )}
          Concurrency {concurrency}. Estimated:{' '}
          <strong>~{etaMin} min</strong>. Keep this tab open.
        </p>
        <div className="flex gap-2">
          <button
            onClick={run}
            className="px-3 py-1.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-sm rounded hover:bg-amber-500/20 transition-colors"
          >
            Start re-analysis
          </button>
          <button
            onClick={() => setConfirmOpen(false)}
            className="px-3 py-1.5 bg-white/5 border border-orbital-border text-gray-400 text-sm rounded hover:bg-white/10 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  // ── Render: idle state ──────────────────────────────────────
  const resultSummary =
    state.done > 0
      ? ` · last run: ${state.ok} ok, ${state.errors} errors`
      : '';

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={() => setConfirmOpen(true)}
        disabled={companies.length === 0}
        className="px-3 py-1.5 bg-white/5 border border-orbital-border text-gray-400 text-sm rounded hover:bg-white/10 disabled:opacity-30 transition-colors"
      >
        {analyzedIds
          ? `Analyze pending (${companies.filter((c) => !analyzedIds.has(c.id)).length})`
          : `Re-analyze all (${companies.length})`}
      </button>
      <button
        onClick={exportJson}
        disabled={companies.length === 0 || exporting}
        className="px-3 py-1.5 bg-white/5 border border-orbital-border text-gray-400 text-sm rounded hover:bg-white/10 disabled:opacity-30 transition-colors"
      >
        {exporting ? 'Exporting...' : 'Export JSON'}
      </button>
      {state.failedNames.length > 0 && (
        <span className="text-[10px] text-gray-600">
          {state.failedNames.length} failed last run
        </span>
      )}
      {resultSummary && (
        <span className="text-[10px] text-gray-600">{resultSummary}</span>
      )}
    </div>
  );
}