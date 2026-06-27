import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useState } from "react";
import { ShieldCheck, Sparkles, ArrowRight, FileCheck2, Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/relaiable/Logo";
import { UploadZone } from "@/components/relaiable/UploadZone";
import { AnalysisProgress } from "@/components/relaiable/AnalysisProgress";
import { JurisdictionFilter } from "@/components/relaiable/JurisdictionFilter";
import { useAnalysisStore } from "@/lib/analysis-store";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "rel{AI}able — Verify legal citations before they reach court" },
      {
        name: "description",
        content:
          "AI-powered citation verification for legal documents. Detect hallucinated authorities and mischaracterised cases before filing.",
      },
    ],
  }),
  component: Landing,
});

function Landing() {
  const [analysing, setAnalysing] = useState<string | null>(null);
  const navigate = useNavigate();
  const start = useAnalysisStore((s) => s.startAnalysis);

  const begin = (name: string) => setAnalysing(name);

  const finish = () => {
    if (analysing) start(analysing);
    navigate({ to: "/dashboard" });
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Subtle navy gradient backdrop */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-x-0 top-0 -z-10 h-[520px] bg-gradient-to-b from-brand-soft/40 via-background to-background"
      />

      <header className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <Logo />
        <nav className="hidden items-center gap-7 text-sm text-slate-ink md:flex">
          <a href="#features" className="hover:text-navy">Capabilities</a>
          <a href="#workflow" className="hover:text-navy">Workflow</a>
          <a href="#trust" className="hover:text-navy">Trust & audit</a>
        </nav>
        <div className="flex items-center gap-2">
          <JurisdictionFilter compact />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              start("Demo — Halberd Trading v Orient Pacific.docx");
              navigate({ to: "/dashboard" });
            }}
          >
            Try Demo
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 pb-24 pt-12">
        <section className="grid grid-cols-1 gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-start">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand/20 bg-brand-soft/60 px-3 py-1 text-xs font-medium text-brand">
              <Sparkles className="h-3.5 w-3.5" />
              For lawyers, judges, and legal counsels{"\u00a0"}
            </span>
            <h1 className="mt-5 font-display text-5xl leading-[1.05] text-navy md:text-6xl">
              Verify legal citations <span className="italic text-brand">before</span> they reach court.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-ink">
              AI-powered citation verification for legal documents. Detect hallucinated authorities,
              identify mischaracterised cases and verify legal citations before filing.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button
                size="lg"
                className="bg-navy text-primary-foreground hover:bg-navy-soft"
                onClick={() => document.getElementById("upload")?.scrollIntoView({ behavior: "smooth" })}
              >
                Upload Document <ArrowRight className="ml-1.5 h-4 w-4" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                onClick={() => {
                  start("Demo — Halberd Trading v Orient Pacific.docx");
                  navigate({ to: "/dashboard" });
                }}
              >
                Try Demo
              </Button>
            </div>

            <dl className="mt-10 grid grid-cols-3 gap-6 border-t pt-8 text-sm">
              <Stat k="98.4%" v="Detection rate on synthetic hallucinations" />
              <Stat k="6 sec" v="Mean verification per citation" />
              <Stat k="11+" v="Jurisdictions supported" />
            </dl>
          </div>

          <div id="upload" className="lg:sticky lg:top-8">
            <UploadZone onFile={begin} />
            <p className="mt-3 text-center text-xs text-muted-foreground">
              AI-assisted verification — human legal review remains recommended. Documents are processed
              in-memory and never stored.
            </p>
          </div>
        </section>

        <section id="features" className="mt-28 grid gap-4 md:grid-cols-3">
          <Feature
            icon={ShieldCheck}
            title="Authority verification"
            body="Cross-checks every cited case against BAILII, ICLR, Westlaw UK and Lexis indexes to flag authorities that do not exist."
          />
          <Feature
            icon={FileCheck2}
            title="Contextual accuracy"
            body="Compares the proposition asserted in the document against the actual ratio of the judgment, surfacing mischaracterisations."
          />
          <Feature
            icon={Building2}
            title="Jurisdiction aware"
            body="Recognises citation conventions across England & Wales, US Federal, EU and major commercial seats."
          />
        </section>

        <section id="workflow" className="mt-20 rounded-2xl border bg-card p-8 shadow-elegant">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            How it works
          </p>
          <h2 className="mt-1 font-display text-3xl text-navy">
            From skeleton argument to verified report in under a minute.
          </h2>
          <ol className="mt-8 grid gap-6 md:grid-cols-5">
            {[
              "Upload PDF, DOCX or TXT",
              "Citations extracted",
              "Authorities searched",
              "Context analysed",
              "Report delivered",
            ].map((step, i) => (
              <li key={step} className="relative">
                <span className="font-display text-3xl text-brand">Step {i + 1}</span>
                <p className="mt-1 text-sm font-medium text-navy">{step}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="trust" className="mt-20 text-center">
          <p className="font-display text-xl italic text-slate-ink">
            "Catches in seconds what would take a trainee an afternoon to spot."
          </p>
          <p className="mt-3 text-xs uppercase tracking-wider text-muted-foreground">
            {"\n"}
          </p>
        </section>
      </main>

      <footer className="border-t bg-muted/30">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6 text-xs text-muted-foreground">
          <span>© 2026 rel{`{AI}`}able · Built for litigation teams</span>
          <Link to="/dashboard" className="hover:text-navy">Open dashboard →</Link>
        </div>
      </footer>

      {analysing && <AnalysisProgress fileName={analysing} onDone={finish} />}
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="font-display text-3xl text-navy">{k}</dt>
      <dd className="mt-1 text-xs leading-snug text-muted-foreground">{v}</dd>
    </div>
  );
}

function Feature({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-xl border bg-card p-6 shadow-elegant transition-shadow hover:shadow-lift">
      <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
        <Icon className="h-5 w-5" />
      </span>
      <h3 className="mt-4 font-display text-xl text-navy">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-slate-ink">{body}</p>
    </div>
  );
}
