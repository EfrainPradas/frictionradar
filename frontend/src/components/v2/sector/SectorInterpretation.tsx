import { DIMENSION_INTERPRETATION, type SectorAggregate } from '../../../data/mockSector';

interface Props {
  sector: SectorAggregate;
  onGenerateBrief?: () => void;
}

export function SectorInterpretation({ sector, onGenerateBrief }: Props) {
  const interp = DIMENSION_INTERPRETATION[sector.dominantDim];

  return (
    <div className="rounded-lg border border-fr-line bg-fr-paper p-5 flex flex-col h-full">
      <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint">
        Sector Interpretation
      </div>
      <div className="text-[17px] font-semibold text-fr-ink mt-1.5 leading-tight">
        {interp.title}
      </div>
      <p className="text-[12.5px] text-fr-ink-soft leading-relaxed mt-2">
        Across the selected sector, {interp.title.toLowerCase()} appears to be a major source of organizational friction.
      </p>

      <div className="mt-4 space-y-3">
        <SubCard label="What this means" body={interp.means} />
        <SubCard label="Recommended positioning" body={interp.angle} />
      </div>

      <div className="flex-1" />
      <button
        type="button"
        onClick={onGenerateBrief}
        className="mt-5 w-full rounded-md bg-fr-ink text-fr-paper text-[12px] font-semibold py-2.5 hover:bg-fr-ink-soft transition-colors"
      >
        Generate Dimension Brief
      </button>
    </div>
  );
}

function SubCard({ label, body }: { label: string; body: string }) {
  return (
    <div className="rounded-md border border-fr-line bg-fr-paper-2 px-3.5 py-3">
      <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint">{label}</div>
      <div className="text-[12px] text-fr-ink-soft leading-relaxed mt-1">{body}</div>
    </div>
  );
}
