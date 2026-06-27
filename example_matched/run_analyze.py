"""Test the 4th pipeline step (distortion_service.analyze) on the cases
extracted from example_matched/Matched.pdf.

These are FAITHFUL citations: the citing-document claim ("Hackaton Doc") is a
fair characterisation of the source. Expected: classification == "correct" for
both — i.e. NOT flagged as mischaracterised or out_of_context.

source_text uses the real holding language of each case (the resolver would feed
the full source document here); the document's own quoted "Source" fragment from
the PDF is included verbatim inside it.
"""
import sys

sys.path.insert(0, ".")  # run from repo root

from app.services.distortion_service import analyze
from app.services.distortion_backend import get_backend

CASES = [
    {
        "id": 1,
        "case": "Lumley v Gye (1853) 2 E&B 216",
        "relevant_text": (
            "The deliberate procurement of another's contractual default is a "
            "recognised civil wrong, independently actionable."
        ),
        "source_text": (
            "He who procures the wrong is a joint wrongdoer with him who does the "
            "wrong. Procurement of the violation of a right is a cause of action in "
            "all instances where the violation is an actionable wrong, whether the "
            "right be a right of property, or a right founded on contract. He who "
            "maliciously procures a damage to another by violation of his right "
            "ought to be made to indemnify, whether he procures an actionable wrong "
            "or a breach of contract. A person who wrongfully and maliciously, or, "
            "which is the same thing, with notice, interrupts the performance of a "
            "contract is liable to an action."
        ),
    },
    {
        "id": 2,
        "case": "American Cyanamid Co v Ethicon Ltd [1975] AC 396",
        "relevant_text": (
            "For an interlocutory injunction the applicant is not required to "
            "establish a strong prima facie case on the merits."
        ),
        "source_text": (
            "The court no doubt must be satisfied that the claim is not frivolous or "
            "vexatious; in other words, that there is a serious question to be tried. "
            "It is no part of the court's function at this stage of the litigation to "
            "try to resolve conflicts of evidence on affidavit as to facts on which "
            "the claims of either party may ultimately depend, nor to decide "
            "difficult questions of law which call for detailed argument and mature "
            "considerations. The use of such expressions as 'a probability,' 'a prima "
            "facie case,' or 'a strong prima facie case' in the context of the "
            "exercise of a discretionary power to grant an interlocutory injunction "
            "leads to confusion. So unless the material available to the court "
            "fails to disclose that the plaintiff has any real prospect of "
            "succeeding in his claim for a permanent injunction at the trial, the "
            "court should go on to consider the balance of convenience."
        ),
    },
]


def main() -> None:
    backend_name = sys.argv[1] if len(sys.argv) > 1 else "mock"
    backend = get_backend(backend_name)
    print(f"=== analyze() — backend: {backend.name} (expect: correct / NOT flagged) ===\n")
    ok = True
    for c in CASES:
        report, rid = analyze(c["relevant_text"], c["source_text"], backend, id=c["id"])
        flagged = report["classification"] != "correct"
        ok = ok and not flagged
        print(f"[{rid}] {c['case']}")
        print(f"    classification  : {report['classification']}"
              f"  {'<-- FLAGGED (unexpected)' if flagged else 'OK (not flagged)'}")
        print(f"    mischaracterised: {report['mischaracterised_pct']}%")
        print(f"    out_of_context  : {report['out_of_context_pct']}%")
        print(f"    holding (src)   : {report['plain_language_holding'][:120]}")
        if report["premise_summary"]:
            print("    flagged premises:")
            for e in report["premise_summary"]:
                print(f"      - [{e['label']}/{e['level']}] {e['reason']}")
        print()
    print("RESULT:", "PASS — neither faithful citation was flagged"
          if ok else "FAIL — a faithful citation was flagged")


if __name__ == "__main__":
    main()
