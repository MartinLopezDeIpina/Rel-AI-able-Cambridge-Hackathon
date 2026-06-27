import { useEffect, useState } from "react";
import { TopBar } from "@/components/relaiable/TopBar";
import { ExecutiveSummary } from "@/components/relaiable/ExecutiveSummary";
import { SummaryPanel, StatBar, TimelineBar } from "@/components/relaiable/SummaryPanel";
import { CitationCard } from "@/components/relaiable/CitationCard";
import { DocumentPreview } from "@/components/relaiable/DocumentPreview";
import { CitationTable } from "@/components/relaiable/CitationTable";
import { AnalysisDrawer } from "@/components/relaiable/AnalysisDrawer";
import { SubpageFooter, GoBackButton } from "@/components/relaiable/SubpageChrome";

import { type Citation } from "@/lib/mock-citations";
import { useLiveSortedCitations, useReportStatus } from "@/lib/live-data";
import { useAnalysisStore } from "@/lib/analysis-store";

export function DashboardWorkspace({
  embedded = false,
}: {
  embedded?: boolean;
}) {
  const sorted = useLiveSortedCitations();
  const status = useReportStatus();
  const loadReport = useAnalysisStore((s) => s.loadReport);
  const loadConfig = useAnalysisStore((s) => s.loadConfig);

  const [selected, setSelected] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<Citation | null>(null);

  useEffect(() => {
    void loadReport();
    void loadConfig();
  }, [loadReport, loadConfig]);

  useEffect(() => {
    if (!selected && sorted[0]) setSelected(sorted[0].id);
  }, [sorted, selected]);

  return (
    <div className={`flex w-full flex-col bg-background ${embedded ? "h-full min-h-0" : "min-h-screen"}`}>
      <TopBar />
      <main className="mx-auto w-full max-w-[1600px] px-4 py-6 md:px-6">
        <div className="space-y-6">
          <ExecutiveSummary />
          
          <StatBar />


          <CitationTable onOpen={setDrawer} />

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-display text-lg text-navy">
                  Citations
                  {status === "pending" && (
                    <span className="ml-2 inline-flex items-center gap-1.5 align-middle text-xs font-normal text-brand">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand" />
                      Live updating…
                    </span>
                  )}
                </h3>
                <span className="text-xs text-muted-foreground">
                  {sorted.length} extracted · click to locate in document
                </span>
              </div>
              <div className="max-h-[760px] space-y-3 overflow-y-auto pr-1">
                {sorted.map((c) => (
                  <CitationCard
                    key={c.id}
                    citation={c}
                    selected={selected === c.id}
                    onSelect={setSelected}
                  />
                ))}
              </div>
            </section>
            <section className="h-[760px]">
              <DocumentPreview selectedId={selected} onSelect={setSelected} />
            </section>
          </div>

          <TimelineBar />

          <SummaryPanel />
        </div>
      </main>
      <SubpageFooter />
      <AnalysisDrawer citation={drawer} onClose={() => setDrawer(null)} />
      {!embedded && <GoBackButton />}
    </div>
  );
}
