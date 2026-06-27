import { MOCK_CITATIONS, MOCK_DOCUMENT } from "@/lib/mock-citations";
import { ShieldCheck, AlertTriangle, BadgeCheck } from "lucide-react";

export function ExecutiveSummary() {
  const total = MOCK_CITATIONS.length;
  const risky = MOCK_CITATIONS.filter((c) => c.status === "risk").length;
  const mischar = MOCK_CITATIONS.filter((c) => c.status === "mischar").length;
  const review = MOCK_CITATIONS.filter((c) => c.status === "review").length;


  const verdict =
    risky > 0
      ? "Do not file without review"
      : mischar > 0
        ? "Partner review required"
        : "Safe to rely on";

  return (
    <section className="overflow-hidden rounded-2xl border bg-card shadow-elegant">
      <div className="flex flex-col gap-6 p-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-4">
          <div
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${
              risky > 0
                ? "bg-risk/10 text-risk"
                : mischar > 0
                  ? "bg-mischar/10 text-mischar"
                  : "bg-verified/15 text-verified"
            }`}
          >
            {risky > 0 ? (
              <AlertTriangle className="h-6 w-6" />
            ) : mischar > 0 ? (
              <ShieldCheck className="h-6 w-6" />
            ) : (
              <BadgeCheck className="h-6 w-6" />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Executive summary
            </p>
            <h2 className="mt-1 font-display text-2xl leading-tight text-navy md:text-3xl">
              {verdict}.{" "}
              <span className="text-slate-ink">
                {risky} hallucinated, {mischar} mischaracterised and {review} require contextual
                review across {total} citations.
              </span>
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {MOCK_DOCUMENT.name} · analysed {MOCK_DOCUMENT.uploadedAt} by{" "}
              <span className="font-medium text-foreground">{MOCK_DOCUMENT.model}</span>.
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center rounded-xl border bg-muted/40 px-10 py-5">
          <div className="text-center">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
              Action items
            </p>
            <p className="mt-1 font-display text-5xl leading-none text-navy">
              {risky + mischar + review}
            </p>
          </div>
        </div>

      </div>

      <RiskBar />
    </section>
  );
}

function RiskBar() {
  const counts = {
    verified: MOCK_CITATIONS.filter((c) => c.status === "verified").length,
    review: MOCK_CITATIONS.filter((c) => c.status === "review").length,
    mischar: MOCK_CITATIONS.filter((c) => c.status === "mischar").length,
    risk: MOCK_CITATIONS.filter((c) => c.status === "risk").length,
  };
  const total = MOCK_CITATIONS.length;
  return (
    <div className="border-t bg-muted/30 px-6 py-4">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium uppercase tracking-wider text-muted-foreground">
          Overall citation integrity
        </span>
        <div className="flex items-center gap-4 text-slate-ink">
          <Legend dot="bg-verified" label={`Verified ${counts.verified}`} />
          <Legend dot="bg-review" label={`Review ${counts.review}`} />
          <Legend dot="bg-mischar" label={`Mischar ${counts.mischar}`} />
          <Legend dot="bg-risk" label={`Risk ${counts.risk}`} />
        </div>
      </div>
      <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-muted">
        <div className="bg-verified" style={{ width: `${(counts.verified / total) * 100}%` }} />
        <div className="bg-review" style={{ width: `${(counts.review / total) * 100}%` }} />
        <div className="bg-mischar" style={{ width: `${(counts.mischar / total) * 100}%` }} />
        <div className="bg-risk" style={{ width: `${(counts.risk / total) * 100}%` }} />
      </div>
    </div>
  );
}

function Legend({ dot, label }: { dot: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {label}
    </span>
  );
}
