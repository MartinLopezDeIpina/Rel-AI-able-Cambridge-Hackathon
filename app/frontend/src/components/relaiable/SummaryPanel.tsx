import { type Citation } from "@/lib/mock-citations";
import { useReport } from "@/lib/report";

const STATS = (citations: Citation[]) => {
  const total = citations.length;
  return [
    { label: "Total", value: total, bg: "" },
    {
      label: "Verified",
      value: citations.filter((c) => c.status === "verified").length,
      bg: "bg-verified/25",
    },
    {
      label: "Needs review",
      value: citations.filter((c) => c.status === "review").length,
      bg: "bg-review/35",
    },
    {
      label: "Mischar.",
      value: citations.filter((c) => c.status === "mischar").length,
      bg: "bg-mischar/25",
    },
    {
      label: "High risk",
      value: citations.filter((c) => c.status === "risk").length,
      bg: "bg-risk/25",
    },
  ];
};

export function StatBar() {
  const { citations } = useReport();
  const stats = STATS(citations);
  return (
    <div className="flex overflow-hidden rounded-xl border bg-card shadow-elegant">
      {stats.map((s, i) => (
        <div
          key={s.label}
          className={`flex flex-1 flex-col items-center justify-center px-4 py-4 ${s.bg} ${
            i < stats.length - 1 ? "border-r" : ""
          }`}
        >
          <p className="text-[10px] font-medium uppercase tracking-wider text-black/70">
            {s.label}
          </p>
          <p className="font-display text-3xl leading-none text-black">{s.value}</p>
        </div>
      ))}
    </div>
  );
}

export function TimelineBar() {
  const { document } = useReport();
  return (
    <div className="rounded-xl border bg-card p-4 shadow-elegant">
      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        Processing timeline
      </p>
      <ol className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {document.steps.map((s, i) => (
          <li key={i} className="relative">
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-soft font-mono text-[10px] font-medium text-brand ring-2 ring-brand-soft">
                {i + 1}
              </span>
              {i < document.steps.length - 1 && (
                <span className="hidden h-px flex-1 bg-border lg:block" />
              )}
            </div>
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">{s.t}</p>
            <p className="text-sm leading-snug text-foreground">{s.label}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function SummaryPanel() {
  const { document } = useReport();
  const AUDIT_ITEMS: { k: string; v: string }[] = [
    { k: "Model", v: document.model },
    { k: "Jurisdiction", v: document.jurisdiction },
    { k: "Practice area", v: document.practiceArea },
    { k: "Sources", v: "Sources metadata DB · Gemini judge" },
    { k: "Document", v: document.name },
  ];
  return (
    <aside className="w-full rounded-xl border bg-card p-4 shadow-elegant">
      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        Audit trail
      </p>
      <div className="mt-3 flex flex-wrap items-stretch gap-y-3">
        {AUDIT_ITEMS.map((item, i) => (
          <div
            key={item.k}
            className={`flex min-w-0 flex-1 flex-col px-4 ${
              i < AUDIT_ITEMS.length - 1 ? "border-r" : ""
            }`}
          >
            <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">
              {item.k}
            </dt>
            <dd className="mt-1 truncate text-sm font-medium text-foreground">{item.v}</dd>
          </div>
        ))}
      </div>
      <p className="mt-4 border-t pt-3 text-[11px] leading-relaxed text-muted-foreground">
        AI-assisted verification — human legal review remains recommended before
        court filing.
      </p>
    </aside>
  );
}
