import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Scale } from "lucide-react";
import { useAnalysisStore } from "@/lib/analysis-store";

const JURISDICTIONS = [
  "England & Wales",
  "US Federal",
  "European Union",
  "Singapore",
  "Hong Kong SAR",
  "Australia",
];

export function JurisdictionFilter({ compact = false }: { compact?: boolean }) {
  const j = useAnalysisStore((s) => s.jurisdiction);
  const set = useAnalysisStore((s) => s.setJurisdiction);
  return (
    <Select value={j} onValueChange={set}>
      <SelectTrigger
        className={`gap-2 border-border bg-card ${compact ? "h-8 px-3 text-xs" : "h-9"}`}
      >
        <Scale className="h-3.5 w-3.5 text-slate-ink" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {JURISDICTIONS.map((j) => (
          <SelectItem key={j} value={j}>
            {j}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
