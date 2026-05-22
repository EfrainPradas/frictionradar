import { useMemo } from 'react';
import type { CompanySignal } from '../../types/signal';
import { transformSignalToObservation } from '../../services/insightComposer';

interface KeySignal {
  text: string;
  type: string;
  occurrences: number;
  confidence: number | null;
}

interface Props {
  signals: CompanySignal[];
  limit?: number;
}

const HIRING_AREA_LABELS: Record<string, string> = {
  retail_hiring_detected: 'retail',
  distribution_hiring_detected: 'distribution',
  manufacturing_hiring_detected: 'manufacturing',
  technology_hiring_detected: 'technology',
  finance_hiring_detected: 'finance',
  operations_hiring_detected: 'operations',
  marketing_hiring_detected: 'marketing',
  sales_hiring_detected: 'sales',
  customer_success_hiring_detected: 'customer success',
  supply_chain_hiring_detected: 'supply chain',
  hr_people_hiring_detected: 'HR/people',
};

export function KeySignals({ signals, limit = 5 }: Props) {
  const keySignals = useMemo(() => {
    if (!signals || signals.length === 0) return [];

    const hiringAreaTypes = new Set<string>();
    const otherSignals: typeof signals = [];
    for (const sig of signals) {
      const stype = (sig.signal_type || '').toLowerCase();
      if (stype in HIRING_AREA_LABELS || stype === 'job_cards_visible_detected' || stype === 'visible_hiring_area_detected') {
        hiringAreaTypes.add(stype);
      } else {
        otherSignals.push(sig);
      }
    }

    const clusterRows: KeySignal[] = [];
    if (hiringAreaTypes.size >= 2) {
      const areaLabels = Array.from(hiringAreaTypes)
        .map((t) => HIRING_AREA_LABELS[t])
        .filter(Boolean);
      const listed = areaLabels.slice(0, 3).join(', ');
      clusterRows.push({
        text: `Hiring is visible across multiple business areas${areaLabels.length > 0 ? ` (${listed}${areaLabels.length > 3 ? ', …' : ''})` : ''}.`,
        type: 'hiring_breadth_summary',
        occurrences: hiringAreaTypes.size,
        confidence: 0.85,
      });
      clusterRows.push({
        text: 'Current evidence shows broad demand, but not yet a dominant pain area.',
        type: 'broad_demand_summary',
        occurrences: 1,
        confidence: 0.8,
      });
    }

    const grouped = new Map<string, KeySignal>();
    for (const sig of otherSignals) {
      const formatted = transformSignalToObservation(sig.signal_text);
      const key = formatted.toLowerCase();
      const existing = grouped.get(key);
      if (existing) {
        existing.occurrences += 1;
        existing.confidence = Math.max(existing.confidence ?? 0, sig.confidence ?? 0);
      } else {
        grouped.set(key, {
          text: sig.signal_text,
          type: sig.signal_type,
          occurrences: 1,
          confidence: sig.confidence,
        });
      }
    }

    const rest = Array.from(grouped.values()).sort((a, b) => {
      const scoreA = a.occurrences * (a.confidence ?? 0.5);
      const scoreB = b.occurrences * (b.confidence ?? 0.5);
      return scoreB - scoreA;
    });

    return [...clusterRows, ...rest]
      .slice(0, limit)
      .map((sig) => ({
        ...sig,
        formatted:
          sig.type === 'hiring_breadth_summary' || sig.type === 'broad_demand_summary'
            ? sig.text
            : transformSignalToObservation(sig.text),
      }));
  }, [signals, limit]);

  if (keySignals.length === 0) {
    return null;
  }

  const lowSignalCount = signals.length < 3;
  const lowConfidence = keySignals.every(s => (s.confidence ?? 0) < 0.5);

  return (
    <div className="space-y-2">
      {keySignals.map((sig, idx) => (
        <div key={idx} className="flex items-start gap-2">
          <span className="text-xs font-mono text-gray-600 w-4 shrink-0">{idx + 1}.</span>
          <span className="text-sm text-gray-300">{sig.formatted}</span>
          {sig.occurrences > 1 && (
            <span className="text-[10px] text-gray-600">({sig.occurrences}×)</span>
          )}
        </div>
      ))}

      {(lowSignalCount || lowConfidence) && (
        <div className="text-xs text-amber-400/70 mt-2">
          {lowSignalCount && <span>Limited data: only {signals.length} observations. </span>}
          {lowConfidence && <span>Low confidence signals detected.</span>}
        </div>
      )}
    </div>
  );
}