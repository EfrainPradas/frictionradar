import { useMemo } from 'react';
import type { CompanySignal } from '../../types/signal';
import { EmptyState } from '../common/States';

interface GroupedSignal {
  signal_type: string;
  signal_text: string;
  occurrences: number;
  avg_confidence: number | null;
  latest_captured_at: string;
}

function getSignalStrength(confidence: number | null): 'strong' | 'medium' | 'weak' {
  if (confidence === null) return 'weak';
  if (confidence >= 0.8) return 'strong';
  if (confidence >= 0.5) return 'medium';
  return 'weak';
}

function getStrengthStyles(strength: 'strong' | 'medium' | 'weak'): {
  badge: string;
  text: string;
} {
  switch (strength) {
    case 'strong':
      return { badge: 'bg-emerald-100 text-emerald-800', text: 'font-semibold text-gray-900' };
    case 'medium':
      return { badge: 'bg-gray-100 text-gray-700', text: 'font-medium text-gray-700' };
    case 'weak':
      return { badge: 'bg-gray-50 text-gray-400', text: 'text-gray-500' };
  }
}

function formatSignalType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

interface Props {
  signals: CompanySignal[];
  showDeduplicated?: boolean;
}

export function SignalsTable({ signals, showDeduplicated = true }: Props) {
  const groupedSignals = useMemo(() => {
    const groups = new Map<string, GroupedSignal>();

    signals.forEach((sig) => {
      const key = `${sig.signal_type}::${sig.signal_text}`;
      const existing = groups.get(key);

      if (existing) {
        existing.occurrences += 1;
        if (sig.confidence !== null) {
          const prevTotal = (existing.avg_confidence ?? 0) * (existing.occurrences - 1);
          existing.avg_confidence = (prevTotal + sig.confidence) / existing.occurrences;
        }
        if (new Date(sig.captured_at) > new Date(existing.latest_captured_at)) {
          existing.latest_captured_at = sig.captured_at;
        }
      } else {
        groups.set(key, {
          signal_type: sig.signal_type,
          signal_text: sig.signal_text,
          occurrences: 1,
          avg_confidence: sig.confidence,
          latest_captured_at: sig.captured_at,
        });
      }
    });

    return Array.from(groups.values()).sort((a, b) => {
      if (a.occurrences !== b.occurrences) return b.occurrences - a.occurrences;
      return (b.avg_confidence ?? 0) - (a.avg_confidence ?? 0);
    });
  }, [signals]);

  if (signals.length === 0) {
    return (
      <EmptyState
        title="No signals collected yet"
        description="Run a collection to start extracting signals."
      />
    );
  }

  const displaySignals = showDeduplicated ? groupedSignals : signals.map((s) => ({
    signal_type: s.signal_type,
    signal_text: s.signal_text,
    occurrences: 1,
    avg_confidence: s.confidence,
    latest_captured_at: s.captured_at,
  }));

  const hasDuplicates = signals.length > groupedSignals.length;

  return (
    <div className="space-y-3">
      {hasDuplicates && (
        <div className="text-xs text-gray-500">
          Showing {groupedSignals.length} unique signals from {signals.length} occurrences
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              {showDeduplicated && <th className="py-2 px-3 text-left text-xs font-semibold text-gray-400 uppercase">Count</th>}
              <th className="py-2 px-3 text-left text-xs font-semibold text-gray-400 uppercase">Signal Type</th>
              <th className="py-2 px-3 text-left text-xs font-semibold text-gray-400 uppercase">Signal</th>
              <th className="py-2 px-3 text-left text-xs font-semibold text-gray-400 uppercase">Strength</th>
              <th className="py-2 px-3 text-left text-xs font-semibold text-gray-400 uppercase">Latest</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {displaySignals.map((sig, idx) => {
              const strength = getSignalStrength(sig.avg_confidence);
              const styles = getStrengthStyles(strength);
              return (
                <tr key={`${sig.signal_type}-${sig.signal_text}-${idx}`} className="hover:bg-gray-50 transition-colors">
                  {showDeduplicated && (
                    <td className="py-2 px-3 text-gray-500 tabular-nums">
                      {sig.occurrences > 1 ? (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-gray-100 text-xs">
                          {sig.occurrences}×
                        </span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  )}
                  <td className="py-2 px-3">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${styles.badge}`}>
                      {formatSignalType(sig.signal_type)}
                    </span>
                  </td>
                  <td className={`py-2 px-3 max-w-xs ${styles.text}`}>
                    <span className="line-clamp-2">{sig.signal_text}</span>
                  </td>
                  <td className="py-2 px-3 tabular-nums">
                    {sig.avg_confidence !== null ? (
                      <span className={strength === 'strong' ? 'font-semibold text-emerald-600' : strength === 'medium' ? 'text-gray-600' : 'text-gray-400'}>
                        {(sig.avg_confidence * 100).toFixed(0)}%
                      </span>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-gray-400 text-xs whitespace-nowrap">
                    {new Date(sig.latest_captured_at).toLocaleDateString()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}