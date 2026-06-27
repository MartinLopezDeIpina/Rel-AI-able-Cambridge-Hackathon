import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/relaiable/AppSidebar";
import { TopBar } from "@/components/relaiable/TopBar";
import { ExecutiveSummary } from "@/components/relaiable/ExecutiveSummary";
import { SummaryPanel, StatBar, TimelineBar } from "@/components/relaiable/SummaryPanel";
import { CitationCard } from "@/components/relaiable/CitationCard";
import { DocumentPreview } from "@/components/relaiable/DocumentPreview";
import { CitationTable } from "@/components/relaiable/CitationTable";
import { AnalysisDrawer } from "@/components/relaiable/AnalysisDrawer";
import { ReportView } from "@/components/relaiable/ReportView";
import { SORTED_CITATIONS, type Citation } from "@/lib/mock-citations";
import { LayoutDashboard, FileText } from "lucide-react";

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — rel{AI}able" },
      { name: "description", content: "Citation verification dashboard." },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  const [selected, setSelected] = useState<string | null>(SORTED_CITATIONS[0]?.id ?? null);
  const [drawer, setDrawer] = useState<Citation | null>(null);
  const [view, setView] = useState<"dashboard" | "report">("dashboard");

  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full bg-background">
        <AppSidebar />
        <SidebarInset className="min-w-0">
          <TopBar />
          <main className="mx-auto w-full max-w-[1600px] px-4 py-6 md:px-6">
            <div className="no-print mb-5 inline-flex rounded-lg border bg-card p-1 shadow-elegant">
              <ToggleBtn active={view === "dashboard"} onClick={() => setView("dashboard")} icon={LayoutDashboard}>
                Dashboard
              </ToggleBtn>
              <ToggleBtn active={view === "report"} onClick={() => setView("report")} icon={FileText}>
                Partner report
              </ToggleBtn>
            </div>

            {view === "report" ? (
              <ReportView />
            ) : (
              <div className="space-y-6">
                <ExecutiveSummary />
                <StatBar />

                <CitationTable onOpen={setDrawer} />

                <div className="grid gap-6 lg:grid-cols-2">
                  <section className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-display text-lg text-navy">Citations</h3>
                      <span className="text-xs text-muted-foreground">
                        {SORTED_CITATIONS.length} extracted · click to locate in document
                      </span>
                    </div>
                    <div className="max-h-[760px] space-y-3 overflow-y-auto pr-1">
                      {SORTED_CITATIONS.map((c) => (
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
            )}
          </main>
        </SidebarInset>
      </div>
      <AnalysisDrawer citation={drawer} onClose={() => setDrawer(null)} />
    </SidebarProvider>
  );
}

function ToggleBtn({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition ${
        active ? "bg-navy text-primary-foreground" : "text-slate-ink hover:text-navy"
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </button>
  );
}
