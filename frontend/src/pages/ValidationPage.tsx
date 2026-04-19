import { useState, useEffect, useCallback } from 'react';
import { AppLayout } from '../components/layout/AppLayout';
import { validationService, type ValidationState, type ValidationDetail } from '../services/validation';

const POLL_INTERVAL = 1000;

export function ValidationPage() {
  const [state, setState] = useState<ValidationState | null>(null);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await validationService.getStatus();
      setState(data);
      if (data.status === 'running') {
        setPolling(true);
      } else {
        setPolling(false);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to fetch status');
    }
  }, []);

  // Initial load
  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // Polling while running
  useEffect(() => {
    if (!polling) return;
    const id = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [polling, fetchStatus]);

  const handleRun = async () => {
    setError(null);
    try {
      const data = await validationService.trigger();
      setState(data);
      setPolling(true);
    } catch (e: any) {
      setError(e.message || 'Failed to trigger validation');
    }
  };

  const report = state?.report;

  return (
    <AppLayout>
      <div className="max-w-4xl mx-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">System Validation</h1>
            <p className="text-sm text-gray-500 mt-1">
              Run the extraction pipeline test suite
            </p>
          </div>
          <button
            onClick={handleRun}
            disabled={state?.status === 'running'}
            className={`px-5 py-2.5 rounded-md text-sm font-medium transition-colors ${
              state?.status === 'running'
                ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                : 'bg-gray-900 text-white hover:bg-gray-800'
            }`}
          >
            {state?.status === 'running' ? 'Running...' : 'Run Validation'}
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Status bar */}
        <StatusBar state={state} />

        {/* Summary */}
        {report && <SummaryCard report={report} durationMs={state?.duration_ms || 0} />}

        {/* Details */}
        {report && <DetailsTable details={report.details} />}
      </div>
    </AppLayout>
  );
}

function StatusBar({ state }: { state: ValidationState | null }) {
  if (!state || state.status === 'idle') {
    return (
      <div className="mb-6 p-4 bg-gray-50 border border-gray-200 rounded-md">
        <span className="text-sm text-gray-500">No validation run yet. Click "Run Validation" to start.</span>
      </div>
    );
  }

  const colors = {
    running: 'bg-blue-50 border-blue-200 text-blue-700',
    success: 'bg-green-50 border-green-200 text-green-700',
    failed: 'bg-red-50 border-red-200 text-red-700',
  };

  const labels = {
    running: 'Running...',
    success: 'All tests passed',
    failed: 'Some tests failed',
  };

  const color = colors[state.status as keyof typeof colors] || 'bg-gray-50 border-gray-200 text-gray-700';
  const label = labels[state.status as keyof typeof labels] || state.status;

  return (
    <div className={`mb-6 p-4 border rounded-md ${color}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        {state.duration_ms > 0 && (
          <span className="text-xs opacity-70">{state.duration_ms}ms</span>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ report, durationMs }: { report: NonNullable<ValidationState['report']>; durationMs: number }) {
  return (
    <div className="mb-6 grid grid-cols-4 gap-4">
      <Stat label="Total" value={report.total} />
      <Stat label="Passed" value={report.passed} color="text-green-600" />
      <Stat label="Failed" value={report.failed} color={report.failed > 0 ? 'text-red-600' : 'text-gray-400'} />
      <Stat label="Errors" value={report.errors} color={report.errors > 0 ? 'text-orange-600' : 'text-gray-400'} />
    </div>
  );
}

function Stat({ label, value, color = 'text-gray-900' }: { label: string; value: number; color?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-md p-4">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${color}`}>{value}</div>
    </div>
  );
}

function DetailsTable({ details }: { details: ValidationDetail[] }) {
  const [expanded, setExpanded] = useState(false);
  const failures = details.filter(d => d.status !== 'passed');
  const showDetails = expanded ? details : failures.length > 0 ? failures : details;

  return (
    <div className="bg-white border border-gray-200 rounded-md overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700">
          {expanded ? 'All Tests' : failures.length > 0 ? 'Failures & Errors' : 'All Tests'}
        </h3>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          {expanded ? 'Show failures only' : 'Show all'}
        </button>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Test</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 w-20">Status</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Error</th>
          </tr>
        </thead>
        <tbody>
          {showDetails.map((d, i) => (
            <tr key={i} className="border-t border-gray-50">
              <td className="px-4 py-2 font-mono text-xs text-gray-700">{d.name}</td>
              <td className="px-4 py-2">
                <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                  d.status === 'passed' ? 'bg-green-100 text-green-700' :
                  d.status === 'failed' ? 'bg-red-100 text-red-700' :
                  'bg-orange-100 text-orange-700'
                }`}>
                  {d.status}
                </span>
              </td>
              <td className="px-4 py-2 text-xs text-gray-500 max-w-md truncate">
                {d.error || ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
