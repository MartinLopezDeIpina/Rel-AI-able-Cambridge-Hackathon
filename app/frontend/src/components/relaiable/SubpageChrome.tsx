import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

export function SubpageFooter() {
  return (
    <footer className="no-print border-t bg-muted/30">
      <div className="mx-auto max-w-7xl px-6 py-6 text-center text-xs text-muted-foreground">
        {"\u00a0"}2026 rel{`{AI}`}able · Built for lawyers and explorers
      </div>
    </footer>
  );
}

export function GoBackButton() {
  const navigate = useNavigate();
  const handleClick = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      window.history.back();
    } else {
      navigate({ to: "/dashboard" });
    }
  };
  return (
    <button
      type="button"
      onClick={handleClick}
      className="no-print fixed bottom-5 right-5 z-40 inline-flex items-center gap-1.5 rounded-full border bg-card/90 px-3.5 py-2 text-xs font-medium text-slate-ink shadow-elegant backdrop-blur transition hover:text-navy hover:shadow-lift"
      aria-label="Go back"
    >
      <ArrowLeft className="h-3 w-3" />
      Go back
    </button>
  );
}
