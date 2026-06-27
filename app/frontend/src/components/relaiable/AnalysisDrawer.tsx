import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { StatusBadge } from "./StatusBadge";
import { ConfidenceBar } from "./ConfidenceBar";
import type { Citation } from "@/lib/mock-citations";
import { Button } from "@/components/ui/button";
import { ExternalLink, Copy } from "lucide-react";

export function AnalysisDrawer({
  citation,
  onClose,
}: {
  citation: Citation | null;
  onClose: () => void;
}) {
  return (
    <Sheet open={!!citation} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        {citation && (
          <>
            <SheetHeader className="space-y-3 pb-2">
              <div className="flex items-start justify-between gap-3">
                <StatusBadge status={citation.status} size="md" />
                <span className="text-xs text-muted-foreground">ID {citation.id.toUpperCase()}</span>
              </div>
              <SheetTitle className="font-display text-2xl leading-tight text-navy">
                {citation.caseName}
              </SheetTitle>
              <p className="text-sm text-muted-foreground">
                {citation.court} · {citation.year} ·{" "}
                <span className="font-mono">{citation.citation}</span>
              </p>
            </SheetHeader>

            <div className="mt-4 rounded-lg border bg-muted/40 p-4">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                AI confidence
              </p>
              <div className="mt-2">
                <ConfidenceBar value={citation.confidence} />
              </div>
            </div>

            <div className="mt-6 space-y-6 text-sm">
              <Field label="Original citation as it appears">
                <span className="font-mono">{citation.citation}</span> — {citation.caseName}
              </Field>
              <Field label="Verification">{citation.reasoning}</Field>
              <Field label="Actual legal principle">{citation.holding}</Field>
              <Field label="How the citation was used">{citation.howUsed}</Field>
              <Field label="Potential problem">{citation.issue}</Field>
              <Field label="AI recommendation">{citation.recommendation}</Field>
              {citation.supporting && <Field label="Supporting authority">{citation.supporting}</Field>}
            </div>

            <div className="mt-8 flex flex-wrap gap-2">
              <Button variant="outline" size="sm">
                <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Open in BAILII
              </Button>
              <Button variant="outline" size="sm">
                <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy analysis
              </Button>
            </div>

            <p className="mt-6 text-[11px] text-muted-foreground">
              AI-assisted verification — human legal review remains recommended.
            </p>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="mt-1.5 leading-relaxed text-foreground">{children}</p>
    </div>
  );
}
