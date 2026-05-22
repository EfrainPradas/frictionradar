interface RadarDimension {
  name: string;
  label: string;
  value: number;
  description?: string;
  detectedSignals?: string[];
  strategicImplication?: string;
  recommendedPositioning?: string;
}

interface Props {
  companyName: string;
  dimensions: RadarDimension[];
  dominantDimension?: string;
}

const DIMENSION_DESCRIPTIONS: Record<string, { description: string; implication: string; positioning: string }> = {
  Reporting: {
    description: 'Reporting fragmentation means the company lacks consistent visibility into business metrics across teams.',
    implication: 'Leadership likely makes decisions with incomplete or inconsistent data, creating risk and slowing execution.',
    positioning: 'Position yourself as someone who can build reporting consistency, operational visibility, and cross-functional analytics coordination.',
  },
  Process: {
    description: 'Process inefficiency suggests workflows are manual, inconsistent, or poorly documented.',
    implication: 'Teams spend time on coordination overhead instead of execution, creating friction at every handoff.',
    positioning: 'Position yourself as someone who can streamline processes, reduce coordination overhead, and create scalable workflows.',
  },
  Tooling: {
    description: 'Tooling inconsistency means teams use different or incompatible systems that don\'t communicate well.',
    implication: 'Information gets lost between tools, creating data silos and integration challenges.',
    positioning: 'Position yourself as someone who can consolidate tools, build integrations, and create unified workflows.',
  },
  Scaling: {
    description: 'Scaling strain means the company is growing faster than its operational infrastructure can support.',
    implication: 'Coordination breaks down as teams expand, creating communication gaps and process gaps.',
    positioning: 'Position yourself as someone who can build coordination frameworks and make scaling not hurt.',
  },
  CX: {
    description: 'Customer experience friction suggests the company struggles to deliver consistent customer interactions.',
    implication: 'Customers experience frustration at touchpoints, creating retention risk and reputational damage.',
    positioning: 'Position yourself as someone who can map and improve customer touchpoints for consistent experience.',
  },
};

export function ExecutiveInterpretation({ companyName, dimensions, dominantDimension }: Props) {
  const sortedDimensions = [...dimensions].sort((a, b) => b.value - a.value);
  const topDim = dominantDimension || sortedDimensions[0]?.name;

  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100">
        <h3 className="text-[13px] font-semibold text-slate-800 tracking-wide">
          Organizational Pain Interpretation
        </h3>
        <p className="text-xs text-slate-500 mt-1">
          What {companyName}'s hiring patterns reveal about their internal needs
        </p>
      </div>

      <div className="divide-y divide-slate-100">
        {sortedDimensions.map((dim) => {
          const meta = DIMENSION_DESCRIPTIONS[dim.name] || {};
          const isDominant = dim.name === topDim;
          const valuePercent = Math.round(dim.value * 100);

          return (
            <div key={dim.name} className={`px-5 py-4 ${isDominant ? 'bg-amber-50/30' : ''}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-semibold ${isDominant ? 'text-amber-700' : 'text-slate-700'}`}>
                    {dim.label}
                  </span>
                  {isDominant && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-semibold">
                      Dominant
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${isDominant ? 'bg-amber-400' : 'bg-slate-300'}`}
                      style={{ width: `${valuePercent}%` }}
                    />
                  </div>
                  <span className="text-[11px] font-mono text-slate-500">{valuePercent}%</span>
                </div>
              </div>

              {/* What the pain means */}
              <p className="text-xs text-slate-600 leading-relaxed mb-2">
                {dim.description || meta.description || 'Organizational pressure in this area.'}
              </p>

              {/* Strategic implication */}
              {meta.implication && (
                <p className="text-xs text-slate-500 leading-relaxed mb-2">
                  <span className="font-medium text-slate-600">Implication:</span> {meta.implication}
                </p>
              )}

              {/* Recommended positioning */}
              <div className={`rounded-md p-2.5 ${isDominant ? 'bg-amber-50 border border-amber-200' : 'bg-slate-50 border border-slate-200'}`}>
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-0.5">
                  Recommended Positioning
                </div>
                <p className={`text-xs leading-relaxed ${isDominant ? 'text-amber-800' : 'text-slate-600'}`}>
                  {dim.recommendedPositioning || meta.positioning || 'Position yourself around the specific outcomes this company needs based on their hiring pattern.'}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}