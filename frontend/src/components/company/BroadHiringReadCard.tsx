import type { CompanyEvaluation } from '../../services/analysis';

interface Props {
  evaluation: CompanyEvaluation;
}

export function BroadHiringReadCard({ evaluation }: Props) {
  const ev = evaluation.evidence;
  const kpis = evaluation.kpis;

  const whatWeKnow: string[] = [];
  if (ev.open_positions_count > 0) {
    whatWeKnow.push(`${ev.open_positions_count.toLocaleString()} visible open positions.`);
  }
  if (ev.visible_hiring_areas > 0) {
    whatWeKnow.push(`${ev.visible_hiring_areas} distinct hiring areas visible on the careers page.`);
  }
  if (ev.distinct_signal_types > 0) {
    whatWeKnow.push(`${ev.distinct_signal_types} distinct hiring-related signals captured.`);
  }
  whatWeKnow.push(`Hiring Pressure is ${kpis.hiring_pressure}.`);

  const whatWeDoNotKnow: string[] = [];
  if (ev.parsed_titles === 0) {
    whatWeDoNotKnow.push('No repeated role families have been isolated yet.');
  }
  if (ev.parsed_descriptions === 0) {
    whatWeDoNotKnow.push('No parsed job descriptions are available to cluster by function.');
  }
  if (kpis.function_concentration === 'low') {
    whatWeDoNotKnow.push('Hiring appears broadly distributed; no function is dominant.');
  }
  if (kpis.pain_clarity === 'low') {
    whatWeDoNotKnow.push('The dominant internal pain cannot yet be isolated from the evidence.');
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-700 leading-relaxed">{evaluation.summary}</p>

      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1.5">What we know</p>
        <ul className="space-y-1">
          {whatWeKnow.map((item, idx) => (
            <li key={idx} className="text-sm text-gray-700 flex items-start gap-2">
              <span className="text-emerald-500 mt-0.5">✓</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1.5">What we do not know yet</p>
        <ul className="space-y-1">
          {whatWeDoNotKnow.map((item, idx) => (
            <li key={idx} className="text-sm text-gray-700 flex items-start gap-2">
              <span className="text-amber-500 mt-0.5">?</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded border border-gray-100 bg-gray-50 px-3 py-2">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Next best step</p>
        <p className="text-sm text-gray-700">{evaluation.next_best_step}</p>
      </div>
    </div>
  );
}
