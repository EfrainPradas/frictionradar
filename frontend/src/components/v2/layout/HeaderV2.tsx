import { BreadcrumbNavigation } from './BreadcrumbNavigation';

export function HeaderV2() {
  return (
    <header className="h-[60px] border-b border-fr-line bg-fr-paper px-7 flex items-center justify-between gap-6">
      <BreadcrumbNavigation />
      <div className="flex items-center gap-3">
        <button className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-fr-line text-[12px] text-fr-ink-mute hover:text-fr-ink hover:border-fr-line-strong transition-colors">
          <span className="text-fr-ink-faint font-mono text-[10px]">⌘K</span>
          Search
        </button>
        <span className="flex items-center gap-1.5 text-[11px] text-fr-ink-mute">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          Live
        </span>
      </div>
    </header>
  );
}
