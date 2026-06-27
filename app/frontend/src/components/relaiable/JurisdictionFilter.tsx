import { Scale } from "lucide-react";
import { useAnalysisStore } from "@/lib/analysis-store";

export function JurisdictionFilter({ compact = false }: { compact?: boolean }) {
  const j = useAnalysisStore((s) => s.jurisdiction);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border border-border bg-card text-muted-foreground ${compact ? "h-8 px-3 text-xs" : "h-9 px-4 text-sm"}`}
    >
      <Scale className="h-3.5 w-3.5 text-slate-ink" />
      {j}
    </span>
  );
}
