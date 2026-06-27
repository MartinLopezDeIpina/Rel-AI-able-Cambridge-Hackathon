# HackTheLaw — Documentation

Citation-integrity layer for legal documents (Alderton & Marsh skeleton-argument
scenario). This folder holds the cross-team comparison and the plan to merge the
two existing codebases behind one API + UI.

## Who owns what

| Area | Owner(s) | Codebase |
|------|----------|----------|
| Verification pipeline — resolver, distortion/faithfulness detector, eval harness (CPU-only, offline) | **Leo** | `/home/leo/hackthelaw` (this repo, the "current version") |
| Citation extraction + LLM enrichment + FastAPI service shell | **Martin** | `github_project/Rel-AI-able-Cambridge-Hackathon` (GitHub) |
| Front-end / dashboard (upload-or-paste + colour-coded report) | **Louisa & Kim** | *about to be integrated* on top of the API below |

## Documents

- [`comparison.md`](comparison.md) — what each codebase does, side by side, scored against the challenge requirements. The headline: the two halves are **complementary**, not overlapping.
- [`integration-plan.md`](integration-plan.md) — concrete plan to plug Martin's extraction → Leo's verification, with verified interfaces, the adapters needed, the verdict mapping, and the REST routes the UI will consume.
- [`implementation-status.md`](implementation-status.md) — what's built vs the proposed 8-step workflow + the integration-artifact checklist (tests: 22 passing).
- [`workflow-comparison.md`](workflow-comparison.md) — proposed simplified workflow vs current code: intended simplification, per-step keep/simplify with reasons, reliability, and the Monte-Carlo confidence step.
- [`file-integration-assessment.md`](file-integration-assessment.md) — per Leo file: where it was integrated, redundancy, and a counterargument.
- [`../leo.md`](../leo.md) — which files came from Leo and the bigger-picture changes made to fit them together.

## Decision of record

We **plugged the two codebases together** behind Martin's FastAPI app. Leo's
pipeline is integrated into Martin's existing `app/services/` (no separate
package), the LLM stages reuse Martin's OpenRouter client (Gemini default, all
Nemotron references removed), and the resolver auto-builds its index when missing.
A single document-level verification endpoint is exposed for Louisa & Kim's UI.
See [`integration-plan.md`](integration-plan.md) for the contract.
