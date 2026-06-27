"""Test the 4th pipeline step (distortion_service.analyze) on the cases
extracted from example_mismatched/Mismatched.pdf.

Each case = a citing-document claim ("Hackathon Doc" column) checked against the
resolved source passage ("Source" column). Expected: all three are MISMATCHED
(mischaracterised / out of context), none "correct".
"""
import json
import sys

sys.path.insert(0, ".")  # run from repo root

from app.services.distortion_service import analyze
from app.services.distortion_backend import get_backend

# ---------------------------------------------------------------------------
# Cases lifted verbatim (as far as possible) from Mismatched.pdf.
# relevant_text = what the citing document asserts the case supports.
# source_text   = the resolved source passage the PDF flags as the truth.
# ---------------------------------------------------------------------------
CASES = [
    {
        "id": 1,
        "case": "Anglia Television Ltd v Reed [1972] 1 QB 60",
        "defect": "opposite of the source was cited",
        "relevant_text": (
            "As to the measure of damages, Crestholm relies upon the decision of "
            "the Court of Appeal in Anglia Television Ltd v Reed [1972] 1 QB 60 as "
            "evidence that, on a breach of contract, damages for lost expectations "
            "must be awarded in the amount of all lost profits, with projected "
            "revenues of £47 million serving as the primary basis for calculation, "
            "less saved costs and risk adjustments."
        ),
        "source_text": (
            "Anglia Television do not claim their profit. They cannot say what their "
            "profit would have been on this contract if Mr Reed had come here and "
            "performed it. Anglia Television claim the wasted expenditure they "
            "incurred, not their loss of profits."
        ),
    },
    {
        "id": 2,
        "case": "D.C. Thomson & Co Ltd v Deakin [1952] Ch 646 (CA, 1952)",
        "defect": "case/citation real, but the stated rule is made up",
        "relevant_text": (
            "The Court held in that case that, in instances of direct inducement, it "
            "is unnecessary for the defendant to have specific knowledge of the "
            "precise terms of the contract, provided that it was aware of the "
            "contract's existence."
        ),
        "source_text": (
            "I do not find it necessary for present purposes to deal with these "
            "contentions. The question whether knowledge of the mere existence of "
            "the contract, without knowledge of its terms, suffices is left open and "
            "I express no concluded opinion upon it."
        ),
    },
    {
        "id": 3,
        "case": "Hadley v Baxendale (1854) 9 Ex 341",
        "defect": "rule correctly stated but applied in reverse (case restricts lost-profit recovery)",
        "relevant_text": (
            "Crestholm's projected revenues of £47 million under the Supply Agreement "
            "plainly satisfy the first limb: the immediate and natural consequence of "
            "the procured termination is the loss of the income stream that the Supply "
            "Agreement was specifically designed to generate, recoverable without "
            "showing any special knowledge of the consequences."
        ),
        "source_text": (
            "For such loss would neither have flowed naturally from the breach of this "
            "contract in the great multitude of such cases occurring under ordinary "
            "circumstances, nor were the special circumstances, which, perhaps, would "
            "have made it a reasonable and natural consequence of such breach of "
            "contract, communicated to or known by the defendants."
        ),
    },
]


def main() -> None:
    backend_name = sys.argv[1] if len(sys.argv) > 1 else "mock"
    backend = get_backend(backend_name)
    print(f"=== analyze() — backend: {backend.name} ===\n")
    for c in CASES:
        report, rid = analyze(c["relevant_text"], c["source_text"], backend, id=c["id"])
        print(f"[{rid}] {c['case']}")
        print(f"    PDF defect      : {c['defect']}")
        print(f"    classification  : {report['classification']}")
        print(f"    mischaracterised: {report['mischaracterised_pct']}%")
        print(f"    out_of_context  : {report['out_of_context_pct']}%")
        print(f"    holding (src)   : {report['plain_language_holding'][:120]}")
        if report["premise_summary"]:
            print("    flagged premises:")
            for e in report["premise_summary"]:
                print(f"      - [{e['label']}/{e['level']}] {e['reason']}")
        else:
            print("    flagged premises: (none)")
        print()


if __name__ == "__main__":
    main()
