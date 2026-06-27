import { Search, Download, Printer } from "lucide-react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { JurisdictionFilter } from "./JurisdictionFilter";

export function TopBar() {
  return (
    <header className="no-print sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-card/80 px-4 backdrop-blur">
      <SidebarTrigger />
      <div className="flex-1" />
      <div className="relative hidden md:block">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search citations…"
          className="h-9 w-72 pl-8 bg-background"
        />
      </div>
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
