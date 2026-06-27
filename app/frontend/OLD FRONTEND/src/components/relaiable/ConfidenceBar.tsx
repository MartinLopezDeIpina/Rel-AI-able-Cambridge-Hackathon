function colorFor(c: number) {
  if (c >= 90) return "bg-verified";
  if (c >= 70) return "bg-review";
  if (c >= 40) return "bg-mischar";
  return "bg-risk";
}

export function ConfidenceBar({ value, showLabel = true }: { value: number; showLabel?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={`absolute inset-y-0 left-0 rounded-full transition-all duration-700 ${colorFor(value)}`}
          style={{ width: `${value}%` }}
        />
      </div>
      {showLabel && (
        <span className="w-10 text-right text-xs font-medium tabular-nums text-slate-ink">
          {value}%
        </span>
      )}
    </div>
  );
}
