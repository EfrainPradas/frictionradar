interface CellData {
  sector: string;
  sectorLabel: string;
  function: string;
  functionLabel: string;
  intensity?: number;
  velocity?: number;
  opportunity?: number;
  companyCount?: number;
  dominantPain?: string;
  notableSignals?: string[];
}

interface Props {
  cell: CellData;
  onClose: () => void;
  onCompanyClick?: (companyId: string) => void;
}

const PAIN_LABELS: Record<string, string> = {
  reporting_fragmentation: 'Reporting Fragmentation',
  process_inefficiency: 'Process Inefficiency',
  tooling_inconsistency: 'Tooling Inconsistency',
  scaling_strain: 'Scaling Strain',
  customer_experience_friction: 'Customer Experience Friction',
};

export function CellIntelligenceView({ cell, onClose, onCompanyClick }: Props) {
  const painLabel = cell.dominantPain ? PAIN_LABELS[cell.dominantPain] || cell.dominantPain : null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden shadow-lg max-w-md">
      {/* Header */}
      <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
            {cell.sectorLabel} × {cell.functionLabel}
          </div>
          <h3 className="text-sm font-semibold text-slate-800 mt-0.5">
            Organizational Pain Concentration
          </h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 transition-colors text-lg leading-none"
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {/* Metrics */}
      <div className="px-5 py-3 grid grid-cols-3 gap-3 border-b border-slate-100">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Pain</div>
          <div className="text-lg font-semibold text-slate-800">
            {cell.intensity != null ? Math.round(cell.intensity * 100) : '—'}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Velocity</div>
          <div className="text-lg font-semibold text-slate-800">
            {cell.velocity != null ? `${Math.round(cell.velocity * 100) > 0 ? '+' : ''}${Math.round(cell.velocity * 100)}` : '—'}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Companies</div>
          <div className="text-lg font-semibold text-slate-800">
            {cell.companyCount || '—'}
          </div>
        </div>
      </div>

      {/* Interpretation */}
      <div className="px-5 py-3 space-y-3">
        {painLabel && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1">Dominant Pain</div>
            <div className="inline-flex items-center px-2.5 py-1 rounded-md bg-amber-50 text-amber-700 text-xs font-medium">
              {painLabel}
            </div>
          </div>
        )}

        {/* Sector×Function interpretation */}
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1">What This Means</div>
          <p className="text-xs text-slate-600 leading-relaxed">
            Companies in <span className="font-medium text-slate-700">{cell.sectorLabel}</span> are showing
            concentrated hiring pressure in <span className="font-medium text-slate-700">{cell.functionLabel}</span>,
            suggesting organizational pain in this area. This is where professionals
            with relevant experience are most strategically needed.
          </p>
        </div>

        {/* Positioning recommendation */}
        <div className="rounded-md bg-slate-50 border border-slate-200 p-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1">
            Strategic Positioning
          </div>
          <p className="text-xs text-slate-700 leading-relaxed">
            Position yourself as someone who can address the
            {' '}{painLabel?.toLowerCase() || 'operational challenges'} that
            {cell.sectorLabel} companies are experiencing in their
            {' '}{cell.functionLabel.toLowerCase()} function. Your experience solving
            similar pain is your strongest differentiator.
          </p>
        </div>

        {cell.notableSignals && cell.notableSignals.length > 0 && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1.5">Key Signals</div>
            <ul className="space-y-1">
              {cell.notableSignals.slice(0, 4).map((signal, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-slate-500">
                  <span className="inline-block mt-1 w-1 h-1 rounded-full bg-slate-300 shrink-0" />
                  {signal}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}