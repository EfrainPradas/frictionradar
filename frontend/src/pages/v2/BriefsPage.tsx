export function BriefsPage() {
  return (
    <div className="p-7">
      <div className="mb-6">
        <h1 className="text-[22px] font-semibold text-fr-ink leading-tight">Briefs</h1>
        <p className="text-[13px] text-fr-ink-mute mt-1">
          Executive briefs generated from market, dimension or company scopes.
        </p>
      </div>

      <div className="rounded-lg border border-fr-line bg-fr-paper p-10 flex flex-col items-center justify-center text-center">
        <div className="text-[12px] tracking-[0.1em] font-mono text-fr-ink-faint uppercase mb-3">
          Briefs · Future phase
        </div>
        <div className="text-[16px] text-fr-ink font-medium">Brief archive coming later.</div>
      </div>
    </div>
  );
}
