import { useState } from "react";
import { ChevronDown, Info, BookOpen } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { StatusBadge } from "./StatusBadge";


import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { Citation } from "@/lib/mock-citations";

export function CitationCard({
  citation,
  selected,
  onSelect,
}: {
  citation: Citation;
  selected?: boolean;
  onSelect?: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className={`group rounded-xl border bg-card p-5 shadow-elegant transition-all hover:shadow-lift ${
        selected ? "ring-2 ring-brand/40" : ""
      }`}
      onClick={() => onSelect?.(citation.id)}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h4 className="font-display text-lg leading-tight text-navy">
            {citation.caseName}
          </h4>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {citation.court} · {citation.year} · <span className="font-mono">{citation.citation}</span>
          </p>
        </div>
        <StatusBadge status={citation.status} />
      </div>

      <p className="mt-3 text-sm leading-relaxed text-slate-ink">
        {citation.summary}
      </p>



      <div className="mt-4 flex items-center justify-between">
        <Popover>
          <PopoverTrigger asChild>
            <button
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-brand hover:bg-brand-soft"
              onClick={(e) => e.stopPropagation()}
            >
              <Info className="h-3.5 w-3.5" />
              Why was this flagged?
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-80" align="start">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              AI reasoning
            </p>
            <p className="mt-2 text-sm leading-relaxed text-foreground">
              {citation.reasoning}
            </p>
          </PopoverContent>
        </Popover>
        <button
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-slate-ink hover:text-navy"
          onClick={(e) => {
            e.stopPropagation();
            setOpen((o) => !o);
          }}
        >
          Details
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="mt-4 space-y-3 border-t pt-4 text-sm">
              <p className="leading-relaxed text-foreground">{citation.holding}</p>
              <p className="leading-relaxed text-foreground">{citation.howUsed}</p>

              {citation.supporting && (
                <div className="flex items-start gap-2 rounded-md bg-muted/60 p-3 text-xs text-slate-ink">
                  <BookOpen className="mt-0.5 h-3.5 w-3.5 text-brand" />
                  {citation.supporting}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

