import type { CollectionRun } from '../../types/collection';
import { CollectionStatusBadge } from '../common/Badge';
import { EmptyState } from '../common/States';

interface Props {
  runs: CollectionRun[];
}

export function CollectionRunsTable({ runs }: Props) {
  if (runs.length === 0) {
    return (
      <EmptyState
        title="No collection runs yet"
        description="Trigger a collection from the actions panel above."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            {['Collector', 'Status', 'Started', 'Finished', 'Signals', 'Error'].map(
              (h) => (
                <th
                  key={h}
                  className="py-2 px-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wide"
                >
                  {h}
                </th>
              )
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {runs.map((run) => (
            <tr key={run.id}>
              <td className="py-2 px-3 font-mono text-xs text-gray-600">
                {run.collector_type}
              </td>
              <td className="py-2 px-3">
                <CollectionStatusBadge status={run.status} />
              </td>
              <td className="py-2 px-3 text-xs text-gray-400 whitespace-nowrap">
                {new Date(run.started_at).toLocaleString()}
              </td>
              <td className="py-2 px-3 text-xs text-gray-400 whitespace-nowrap">
                {run.finished_at
                  ? new Date(run.finished_at).toLocaleString()
                  : '—'}
              </td>
              <td className="py-2 px-3 text-xs text-gray-500 tabular-nums">
                {(run.metadata_json as { signals_extracted?: number } | null)
                  ?.signals_extracted ?? '—'}
              </td>
              <td className="py-2 px-3 text-xs text-red-500 max-w-xs">
                {run.error_message ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
