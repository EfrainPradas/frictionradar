interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  return (
    <header className="h-12 flex items-center justify-between border-b border-gray-200 bg-white px-6 shrink-0">
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-semibold text-gray-800">{title}</h1>
        {subtitle && (
          <span className="text-xs text-gray-400">{subtitle}</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 text-xs text-gray-400 font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
          API connected
        </span>
      </div>
    </header>
  );
}
