import { Download, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { JurisdictionFilter } from "./JurisdictionFilter";
import { Logo } from "./Logo";
import { toggleDashboard } from "@/lib/dashboard-toggle";

export function TopBar() {
  return (
    <header className="no-print sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-card/80 px-4 backdrop-blur">
      <button
        onClick={toggleDashboard}
        className="cursor-pointer border-0 bg-transparent p-0"
        aria-label="Toggle workspace navigation"
      >
        <Logo />
      </button>
      <div className="flex-1" />
      <JurisdictionFilter compact />
      <Button
        variant="outline"
        size="sm"
        onClick={() => window.print()}
        className="hidden lg:inline-flex"
      >
        <Printer className="mr-1.5 h-3.5 w-3.5" /> Print
      </Button>
      <Button
        size="sm"
        className="bg-navy text-primary-foreground hover:bg-navy-soft"
        onClick={() => window.print()}
      >
        <Download className="mr-1.5 h-3.5 w-3.5" /> Export PDF
      </Button>
    </header>
  );
}
