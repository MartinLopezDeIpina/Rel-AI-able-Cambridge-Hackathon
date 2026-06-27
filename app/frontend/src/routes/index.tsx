import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useState } from "react";
import { toggleDashboard } from "@/lib/dashboard-toggle";
import { ShieldCheck, Sparkles, FileCheck2, Scale } from "lucide-react";
import { Logo } from "@/components/relaiable/Logo";
import { UploadZone } from "@/components/relaiable/UploadZone";
import { AnalysisProgress } from "@/components/relaiable/AnalysisProgress";

import { useAnalysisStore } from "@/lib/analysis-store";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { verifyFile, toReport } from "@/lib/api";

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
  const setParagraphs = useAnalysisStore((s) => s.setParagraphs);
  const loadReport = useAnalysisStore((s) => s.loadReport);

  // Upload -> POST /verify (the backend runs the pipeline and writes a fresh
  // report.json before responding) -> store paragraphs from the sync response
  // (needed for highlighting), then load the validated report into the store.
  const mutation = useMutation({
    mutationFn: (file: File) => verifyFile(file),
    onSuccess: async (resp, file) => {
      const { paragraphs } = toReport(resp);
      setParagraphs(paragraphs);
      start(file.name);
      await loadReport();
    },
    onError: (err) => {
      setAnalysing(null);
      toast.error("Verification failed", {
        description: String((err as Error)?.message ?? err),
      });
    },
  });

  const begin = (file: File) => {
    setAnalysing(file.name);
    mutation.mutate(file);
  };

  const finish = () => navigate({ to: "/dashboard" });

  return (
    <div className="min-h-screen bg-background">
      {/* Subtle navy gradient backdrop */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-x-0 top-0 -z-10 h-[520px] bg-gradient-to-b from-brand-soft/40 via-background to-background"
      />

      <header className="mx-auto flex max-w-7xl items-center justify-between border-b border-border px-6 py-5">
        <button onClick={toggleDashboard} className="cursor-pointer bg-transparent border-0 p-0"><Logo /></button>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card text-muted-foreground h-8 px-3 text-xs">
            <Scale className="h-3.5 w-3.5 text-slate-ink" />
            UK
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 pb-24 pt-12">
        <section className="flex flex-col gap-12">
          <div className="max-w-3xl">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand/20 bg-brand-soft/60 px-3 py-1 text-xs font-medium text-brand">
              <Sparkles className="h-3.5 w-3.5" />
              For lawyers and explorers{"\u00a0"}
            </span>
            <h1 className="mt-5 font-display text-5xl leading-[1.05] text-navy md:text-6xl">
              Verify legal citations <span className="italic text-brand">before</span> they reach court.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-ink">
              AI-powered citation verification for legal documents. Detect hallucinated authorities,
              identify mischaracterised cases and verify legal citations before filing.
            </p>

            <hr className="mt-8 border-t border-border" />
          </div>

          <div id="upload" className="mx-auto w-full max-w-3xl">
            <UploadZone onFile={begin} />
            <p className="mt-3 text-center text-xs text-muted-foreground">
              AI-assisted verification — human legal review remains recommended.
            </p>
          </div>

          <dl className="grid grid-cols-3 gap-6 border-t pt-8 text-sm">
            <Stat k="Extract" v="Automatically identify citations" />
            <Stat k="Verify" v="Cross-check legal authorities" />
            <Stat k="Explain" v="Plain-language reasoning for every result" />
          </dl>
        </section>


        <section id="features" className="mt-28 grid gap-4 md:grid-cols-2">
          <Feature
            icon={ShieldCheck}
            title="Authority verification"
            body="Cross-checks the provided Data Base to flag anything suspicious."
          />
          <Feature
            icon={FileCheck2}
            title="Contextual accuracy"
            body="Compares the proposition asserted in the document against the actual ratio of the judgment, surfacing mischaracterisations."
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
              "Upload PDF",
              "Citations extracted",
              "Retrieval from test Data Base",
              "3-level structured approach",
              "Report delivered in natural language",
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
            "Could catch in seconds what could take a trainee an afternoon to spot."
          </p>
          <p className="mt-3 text-xs uppercase tracking-wider text-muted-foreground">
            {"\n"}
          </p>
        </section>
      </main>

      <footer className="border-t bg-muted/30">
        <div className="mx-auto grid max-w-7xl grid-cols-3 items-center px-6 py-6 text-xs text-muted-foreground">
          <span>{"\u00a0"}2026 rel{`{AI}`}able · Built for lawyers and explorers</span>
          <div className="text-center">
            This product was created for a Hackathon and can make mistakes.
          </div>
          <div className="text-right">
            <Link to="/about" className="hover:text-navy">
              About Us
            </Link>
          </div>
        </div>
      </footer>


      {analysing && (mutation.isPending || mutation.isSuccess) && (
        <AnalysisProgress
          fileName={analysing}
          done={mutation.isSuccess}
          onDone={finish}
        />
      )}
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
