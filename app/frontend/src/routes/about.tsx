import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { SubpageFooter, GoBackButton } from "@/components/relaiable/SubpageChrome";

import { Logo } from "@/components/relaiable/Logo";
import aboutTeam from "@/assets/team-photo.jpg.asset.json";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "About us — rel{AI}able" },
      {
        name: "description",
        content:
          "The team behind rel{AI}able — law and CS/ML students building citation integrity tools for legal professionals.",
      },
      { property: "og:title", content: "About us — rel{AI}able" },
      {
        property: "og:description",
        content:
          "Law and CS/ML students building citation integrity tools for legal professionals.",
      },
    ],
  }),
  component: AboutPage,
});

function AboutPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <Link to="/"><Logo /></Link>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-slate-ink hover:text-navy"
        >
          <ArrowLeft className="h-4 w-4" /> Back home
        </Link>
      </header>

      <main className="mx-auto max-w-4xl px-6 pb-24 pt-8">
        <h1 className="text-center font-display text-5xl text-navy md:text-6xl">
          This is us!
        </h1>

        <section className="mt-12">
          <div className="overflow-hidden rounded-2xl border bg-card shadow-elegant">
            <img
              src={aboutTeam.url}
              alt="The rel{AI}able team — law and CS/ML students collaborating"
              width={1280}
              height={768}
              loading="lazy"
              className="h-auto w-full object-cover"
            />
          </div>
        </section>

        <section className="mt-10 space-y-6 text-slate-ink">
          <h2 className="font-display text-3xl text-navy">Our mission</h2>
          <p className="text-lg leading-relaxed">
            rel{`{AI}`}able exists to safeguard the integrity of legal citations in
            an era where AI-generated drafts are entering courtrooms at unprecedented
            speed. Our platform verifies whether cited authorities actually exist,
            and whether they have been correctly applied — before a document ever
            reaches a judge.
          </p>
          <p className="leading-relaxed">
            We believe that trust, accuracy and transparency are non-negotiable in
            legal workflows. Every fabricated citation undermines the profession;
            every mischaracterised authority erodes confidence in the system. Our
            tooling is designed to give litigators, judges and in-house counsel a
            fast, auditable second pair of eyes.
          </p>

          <h2 className="pt-4 font-display text-3xl text-navy">Who we are</h2>
          <p className="leading-relaxed">
            We are a small, interdisciplinary team — a mix of law students and
            computer science / machine learning students. The blend matters: legal
            judgment shapes what we verify, and modern ML shapes how reliably we can
            do it. Together we are building the kind of product we would want a
            magic-circle firm, a chambers, or a judicial assistant to rely on.
          </p>
        </section>
      </main>

      <SubpageFooter />
      <GoBackButton />
    </div>
  );
}

