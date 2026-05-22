interface EmptyStateProps {
  title: string;
  description?: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-10 h-10 rounded-full bg-[#101418] border border-orbital-border flex items-center justify-center mb-3">
        <span className="text-gray-600 text-lg">—</span>
      </div>
      <p className="text-sm font-medium text-gray-400">{title}</p>
      {description && (
        <p className="text-xs text-gray-600 mt-1 max-w-xs">{description}</p>
      )}
    </div>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <svg
          className="animate-spin h-4 w-4 text-amber-500/60"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v8H4z"
          />
        </svg>
        {label}
      </div>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-400">
      <strong className="font-medium text-red-300">Error: </strong>
      {message}
    </div>
  );
}

export function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-orbital-border bg-[#0b0f12]">
      <div className="border-b border-orbital-border px-5 py-3">
        <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500">{title}</h3>
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}