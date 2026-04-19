interface ActionButtonProps {
  label: string;
  isLoading: boolean;
  onClick: () => void;
  disabled?: boolean;
}

function ActionButton({ label, isLoading, onClick, disabled }: ActionButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={isLoading || disabled}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      {isLoading ? (
        <svg className="animate-spin h-3.5 w-3.5 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      ) : null}
      {isLoading ? 'Analyzing...' : label}
    </button>
  );
}

interface Props {
  onRecalculate: () => void;
  isRecalculating: boolean;
}

export function ActionPanel({
  onRecalculate,
  isRecalculating,
}: Props) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <ActionButton
        label="Analyze Company"
        isLoading={isRecalculating}
        onClick={onRecalculate}
        disabled={isRecalculating}
      />
    </div>
  );
}
