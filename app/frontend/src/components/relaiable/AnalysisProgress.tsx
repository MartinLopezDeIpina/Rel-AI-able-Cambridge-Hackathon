import { useEffect, useState } from "react";
import { Logo } from "./Logo";

const MESSAGES = [
  "Analysing document…",
  "Parsing document structure…",
  "Extracting citations…",
  "Searching legal databases…",
  "Checking citations against authorities…",
  "Analysing context & application…",
  "Generating reliability report…",
];

const TICK_MS = 550;

export function AnalysisProgress({
  fileName,
  onDone,
}: {
  fileName: string;
  onDone: () => void;
}) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (tick >= MESSAGES.length) {
      const t = setTimeout(onDone, 500);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setTick((s) => s + 1), TICK_MS);
    return () => clearTimeout(t);
  }, [tick, onDone]);

  const message = MESSAGES[Math.min(tick, MESSAGES.length - 1)];
  const pct = Math.min(100, Math.round((tick / MESSAGES.length) * 100));

  // Circle geometry
  const R = 32;
  const C = 2 * Math.PI * R;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/95 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border bg-card p-8 text-center shadow-lift">
        <div className="flex justify-center">
          <Logo />
        </div>

        <div className="mt-8 flex justify-center">
          <div className="relative h-20 w-20">
            <svg className="h-20 w-20 -rotate-90" viewBox="0 0 80 80">
              <circle
                cx="40"
                cy="40"
                r={R}
                strokeWidth="5"
                className="fill-none stroke-muted"
              />
              <circle
                cx="40"
                cy="40"
                r={R}
                strokeWidth="5"
                strokeLinecap="round"
                className="fill-none stroke-brand animate-[spin_1.4s_linear_infinite] origin-center"
                strokeDasharray={`${C * 0.28} ${C}`}
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center font-mono text-xs tabular-nums text-brand">
              {pct}%
            </div>
          </div>
        </div>

        <p
          key={message}
          className="mt-6 animate-fade-in text-sm font-medium text-navy"
        >
          {message}
        </p>
        <p className="mt-2 truncate text-xs text-muted-foreground">{fileName}</p>

        <div className="mx-auto mt-6 h-1 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-brand transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>

        <p className="mt-6 text-[11px] leading-relaxed text-muted-foreground">
          AI-assisted verification — human legal review remains recommended.
        </p>
      </div>
    </div>
  );
}
