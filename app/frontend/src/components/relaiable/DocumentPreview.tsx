import { MOCK_DOC_PARAGRAPHS, MOCK_CITATIONS } from "@/lib/mock-citations";
import type { CitationStatus } from "@/lib/mock-citations";
import { useEffect, useRef } from "react";

const HIGHLIGHT: Record<CitationStatus, string> = {
  verified: "bg-verified/15 decoration-verified",
  review: "bg-review/25 decoration-review",
  mischar: "bg-mischar/20 decoration-mischar",
  risk: "bg-risk/15 decoration-risk",
};

export function DocumentPreview({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!selectedId) return;
    const el = scrollerRef.current?.querySelector(`[data-citation-id="${selectedId}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selectedId]);

  return (
    <div className="flex h-full flex-col rounded-xl border bg-card shadow-elegant">
      <div className="flex items-center justify-between border-b px-5 py-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Document preview</p>
          <p className="text-sm font-medium text-navy">Skeleton Argument</p>
        </div>
        <p className="text-xs text-muted-foreground">10 of 47 pages</p>
      </div>
      <div ref={scrollerRef} className="prose-legal flex-1 overflow-y-auto px-7 py-6 text-[13.5px] leading-7 text-foreground">
        {MOCK_DOC_PARAGRAPHS.map((p, idx) => {
          const cite = MOCK_CITATIONS.find((c) => c.paragraph === idx);
          if (!cite) return <p key={idx} className="mb-4">{p}</p>;
          const re = new RegExp(`(${cite.caseName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`);
          const parts = p.split(re);
          return (
            <p key={idx} className="mb-4">
              <span className="mr-2 select-none text-xs text-muted-foreground">{idx + 1}.</span>
              {parts.map((part, i) =>
                part === cite.caseName ? (
                  <button
                    key={i}
                    data-citation-id={cite.id}
                    onClick={() => onSelect(cite.id)}
                    className={`rounded px-1 underline decoration-2 underline-offset-4 transition ${HIGHLIGHT[cite.status]} ${
                      selectedId === cite.id ? "ring-2 ring-brand/40" : ""
                    }`}
                  >
                    {part}
                  </button>
                ) : (
                  <span key={i}>{part}</span>
                ),
              )}
            </p>
          );
        })}
      </div>
    </div>
  );
}
