import { createFileRoute, Link } from "@tanstack/react-router";
import { ReportView } from "@/components/relaiable/ReportView";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Printer } from "lucide-react";

export const Route = createFileRoute("/report")({
  head: () => ({
    meta: [
      { title: "Citation report — rel{AI}able" },
      { name: "description", content: "Concise partner-ready citation verification report." },
    ],
  }),
  component: ReportPage,
});

function ReportPage() {
  return (
    <div className="min-h-screen bg-background py-10">
      <div className="no-print mx-auto mb-6 flex max-w-3xl items-center justify-between px-4">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/dashboard">
            <ArrowLeft className="mr-1.5 h-4 w-4" /> Back to dashboard
          </Link>
        </Button>
        <Button
          size="sm"
          className="bg-navy text-primary-foreground hover:bg-navy-soft"
          onClick={() => window.print()}
        >
          <Printer className="mr-1.5 h-3.5 w-3.5" /> Print / Export PDF
        </Button>
      </div>
      <div className="px-4">
        <ReportView />
      </div>
    </div>
  );
}
