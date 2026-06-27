export type CitationStatus = "verified" | "review" | "mischar" | "risk";

export interface Citation {
  id: string;
  caseName: string;
  court: string;
  year: number;
  citation: string;
  summary: string;
  status: CitationStatus;
  confidence: number;
  holding: string;
  howUsed: string;
  reasoning: string;
  recommendation: string;
  supporting?: string;
  issue: string;
  action: string;
  // Index of paragraph in mock document where citation appears
  paragraph: number;
  // Semantic-entropy uncertainty (0..1 normalised) that the source supports the
  // citation — only present for live results; higher = the model is less certain.
  uncertainty?: number | null;
}

export const STATUS_META: Record<
  CitationStatus,
  { label: string; tone: string; dot: string; description: string }
> = {
  verified: {
    label: "Verified",
    tone: "verified",
    dot: "bg-verified",
    description: "Exists and correctly applied.",
  },
  review: {
    label: "Needs Review",
    tone: "review",
    dot: "bg-review",
    description: "Exists; minor contextual inaccuracies.",
  },
  mischar: {
    label: "Mischaracterised",
    tone: "mischar",
    dot: "bg-mischar",
    description: "Real authority materially misrepresented.",
  },
  risk: {
    label: "High Risk",
    tone: "risk",
    dot: "bg-risk",
    description: "Cannot be verified — likely hallucinated.",
  },
};

export const MOCK_CITATIONS: Citation[] = [
  {
    id: "c1",
    caseName: "Hadley v Baxendale",
    court: "Court of Exchequer",
    year: 1854,
    citation: "(1854) 9 Exch 341",
    summary:
      "Established the foundational rule on remoteness of damages in contract.",
    status: "verified",
    confidence: 98,
    holding:
      "Damages recoverable are those arising naturally from the breach, or such as may reasonably be supposed to have been in the contemplation of both parties at the time of contracting.",
    howUsed:
      "Cited to support the Claimant's argument that loss of profits was within the parties' reasonable contemplation.",
    reasoning:
      "The proposition asserted in the document aligns exactly with the holding. Citation form is correct and the authority remains good law.",
    recommendation: "No action required.",
    supporting: "Affirmed in Victoria Laundry (Windsor) Ltd v Newman Industries Ltd [1949] 2 KB 528.",
    issue: "None",
    action: "Retain",
    paragraph: 0,
  },
  {
    id: "c2",
    caseName: "Donoghue v Stevenson",
    court: "House of Lords",
    year: 1932,
    citation: "[1932] AC 562",
    summary:
      "Foundational authority for the modern law of negligence and the neighbour principle.",
    status: "verified",
    confidence: 99,
    holding:
      "A manufacturer owes a duty of care to the ultimate consumer of its product where intermediate examination is not reasonably expected.",
    howUsed: "Used to introduce the general duty of care framework.",
    reasoning:
      "Direct quotation of Lord Atkin's speech matches the official report.",
    recommendation: "No action required.",
    issue: "None",
    action: "Retain",
    paragraph: 1,
  },
  {
    id: "c3",
    caseName: "American Cyanamid Co v Ethicon Ltd",
    court: "House of Lords",
    year: 1975,
    citation: "[1975] AC 396",
    summary:
      "Governing test for the grant of interlocutory injunctions in England & Wales.",
    status: "review",
    confidence: 81,
    holding:
      "The court must be satisfied that there is a serious question to be tried; the balance of convenience then determines whether to grant the injunction.",
    howUsed:
      "Cited for the proposition that the Claimant must demonstrate a 'strong prima facie case'.",
    reasoning:
      "American Cyanamid rejected the 'prima facie case' threshold in favour of 'serious question to be tried'. The document overstates the threshold.",
    recommendation:
      "Reformulate the threshold to match American Cyanamid or cite a narrow line of authority (e.g. NWL Ltd v Woods) that retains the higher test.",
    supporting: "See also Series 5 Software Ltd v Clarke [1996] 1 All ER 853.",
    issue: "Threshold misstated",
    action: "Revise paragraph 14",
    paragraph: 2,
  },
  {
    id: "c4",
    caseName: "Lumley v Gye",
    court: "Court of Queen's Bench",
    year: 1853,
    citation: "(1853) 2 E & B 216",
    summary: "Established the tort of inducing breach of contract.",
    status: "verified",
    confidence: 95,
    holding:
      "A person who knowingly and without justification procures a breach of contract between two others is liable in tort to the innocent party.",
    howUsed: "Cited as the origin of the economic tort relied upon at §22.",
    reasoning: "Holding accurately summarised.",
    recommendation: "No action required.",
    issue: "None",
    action: "Retain",
    paragraph: 3,
  },
  {
    id: "c5",
    caseName: "Photo Production Ltd v Securicor Transport Ltd",
    court: "House of Lords",
    year: 1980,
    citation: "[1980] AC 827",
    summary:
      "Confirmed that exclusion clauses are a matter of construction, not a rule of law on fundamental breach.",
    status: "verified",
    confidence: 93,
    holding:
      "There is no rule of law preventing parties from contracting out of liability for fundamental breach; the question is one of construction of the clause.",
    howUsed: "Cited at §31 to defeat the Claimant's fundamental breach argument.",
    reasoning: "Citation accurate and correctly applied to the facts.",
    recommendation: "No action required.",
    issue: "None",
    action: "Retain",
    paragraph: 4,
  },
  {
    id: "c6",
    caseName: "Marshall v Westbridge Holdings Ltd",
    court: "Court of Appeal",
    year: 2022,
    citation: "[2022] EWCA Civ 1184",
    summary: "Purportedly recognising a duty of disclosure in arm's-length commercial negotiations.",
    status: "risk",
    confidence: 12,
    holding:
      "No matching authority located in the National Archives caselaw service, BAILII, ICLR or Westlaw UK indexes for this neutral citation.",
    howUsed:
      "Relied upon at §47 as the leading modern authority on pre-contractual disclosure between sophisticated commercial parties.",
    reasoning:
      "The neutral citation [2022] EWCA Civ 1184 does not correspond to a published Court of Appeal judgment under this name. The proposition contradicts Smith v Hughes (1871) and the line of authority following Bell v Lever Brothers. Highly likely to be a hallucinated authority.",
    recommendation:
      "Remove the citation entirely and reframe the disclosure argument by reference to genuine authority (e.g. HIH Casualty v Chase Manhattan Bank [2003] UKHL 6).",
    issue: "Authority cannot be located",
    action: "Remove and reframe",
    paragraph: 5,
  },
  {
    id: "c7",
    caseName: "Cavendish Square Holding BV v Talal El Makdessi",
    court: "Supreme Court",
    year: 2015,
    citation: "[2015] UKSC 67",
    summary: "Modern restatement of the penalty doctrine in English contract law.",
    status: "mischar",
    confidence: 58,
    holding:
      "A clause is penal only if it imposes a detriment out of all proportion to any legitimate interest of the innocent party in enforcement of the primary obligation.",
    howUsed:
      "Cited at §38 for the proposition that any clause exceeding a 'genuine pre-estimate of loss' is unenforceable.",
    reasoning:
      "The Supreme Court expressly moved away from the 'genuine pre-estimate of loss' formulation derived from Dunlop. The document applies the older Dunlop test under the guise of Cavendish, materially mischaracterising the current law.",
    recommendation:
      "Replace the 'genuine pre-estimate of loss' formulation with the Cavendish 'legitimate interest / proportionality' test.",
    supporting: "Cf. Dunlop Pneumatic Tyre Co Ltd v New Garage [1915] AC 79.",
    issue: "Wrong test applied",
    action: "Revise paragraph 38",
    paragraph: 6,
  },
  {
    id: "c8",
    caseName: "Ashcroft v Pemberton Chambers LLP",
    court: "High Court",
    year: 2021,
    citation: "[2021] EWHC 2099 (Comm)",
    summary: "Allegedly extending fiduciary duties to non-equity members of an LLP.",
    status: "risk",
    confidence: 18,
    holding:
      "No such judgment located on BAILII or in the Commercial Court list for the neutral citation [2021] EWHC 2099 (Comm), which corresponds to a different reported decision.",
    howUsed:
      "Cited at §52 as authority for a novel fiduciary duty owed by junior LLP members.",
    reasoning:
      "Neutral citation conflicts with a different reported decision under the same number. No matching case name appears in major databases. The proposition is also inconsistent with F&C Alternative Investments v Barthelemy [2011] EWHC 1731 (Ch).",
    recommendation:
      "Remove. Consider F&C Alternative Investments v Barthelemy as substitute authority if a fiduciary point must be advanced.",
    issue: "Citation does not correspond to any reported case",
    action: "Remove",
    paragraph: 7,
  },
  {
    id: "c9",
    caseName: "Investors Compensation Scheme Ltd v West Bromwich BS",
    court: "House of Lords",
    year: 1998,
    citation: "[1998] 1 WLR 896",
    summary: "Lord Hoffmann's restatement of the principles of contractual interpretation.",
    status: "verified",
    confidence: 96,
    holding:
      "Contracts are to be interpreted by reference to the meaning the document would convey to a reasonable person having all the background knowledge reasonably available to the parties at the time of contracting.",
    howUsed: "Cited at §60 to frame the construction exercise.",
    reasoning: "Citation and proposition both accurate.",
    recommendation: "No action required.",
    issue: "None",
    action: "Retain",
    paragraph: 8,
  },
  {
    id: "c10",
    caseName: "Arnold v Britton",
    court: "Supreme Court",
    year: 2015,
    citation: "[2015] UKSC 36",
    summary: "Reasserted the primacy of the natural meaning of contractual language.",
    status: "review",
    confidence: 74,
    holding:
      "Commercial common sense and surrounding circumstances should not be invoked to undervalue the importance of the language actually used.",
    howUsed:
      "Cited at §63 alongside ICS for a unified 'commercial common sense' approach.",
    reasoning:
      "Arnold v Britton is often read as a corrective to ICS. Presenting the two as a single permissive approach understates the tension between them; reviewing partner may wish to acknowledge the line of authority more carefully.",
    recommendation: "Add a sentence acknowledging the Arnold v Britton corrective.",
    issue: "Authorities presented as harmonious",
    action: "Add nuance at §63",
    paragraph: 9,
  },
];

const STATUS_PRIORITY: Record<CitationStatus, number> = {
  risk: 0,
  mischar: 1,
  review: 2,
  verified: 3,
};

export const SORTED_CITATIONS: Citation[] = [...MOCK_CITATIONS].sort((a, b) => {
  const d = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
  if (d !== 0) return d;
  return a.confidence - b.confidence;
});

export const MOCK_DOC_PARAGRAPHS = [
  "Damages for loss of profit fall squarely within the rule of remoteness articulated in Hadley v Baxendale, the consequences of the breach having been within the reasonable contemplation of both parties.",
  "The Defendant's duty of care arises from the well-established neighbour principle in Donoghue v Stevenson, applied here to a commercial supply chain.",
  "On the application for interlocutory relief, the Claimant respectfully submits that it has demonstrated a strong prima facie case, satisfying the test in American Cyanamid Co v Ethicon Ltd.",
  "The Third Defendant knowingly induced the breach pleaded at paragraph 18 and is liable under the principle in Lumley v Gye.",
  "The exclusion clause at clause 14.2 falls to be construed as a matter of language, in accordance with Photo Production Ltd v Securicor Transport Ltd, and operates to exclude the heads of loss now claimed.",
  "Sophisticated commercial counterparties owe one another a duty of candid disclosure during negotiations of a transaction of this magnitude: see Marshall v Westbridge Holdings Ltd [2022] EWCA Civ 1184.",
  "Clause 22 is unenforceable as a penalty: it does not represent a genuine pre-estimate of loss within the meaning of Cavendish Square Holding BV v Talal El Makdessi.",
  "Junior members of an LLP owe fiduciary duties to the partnership as a whole, as confirmed in Ashcroft v Pemberton Chambers LLP [2021] EWHC 2099 (Comm).",
  "The contract is to be construed against the matrix of background facts reasonably available to the parties: Investors Compensation Scheme Ltd v West Bromwich BS.",
  "Read together with Arnold v Britton, the proper approach blends commercial common sense with the natural meaning of the words used.",
];

export const MOCK_DOCUMENT = {
  name: "Skeleton Argument — Halberd Trading Ltd v Orient Pacific Shipping Co.docx",
  uploadedAt: "26 Jun 2026, 09:42",
  jurisdiction: "England & Wales",
  practiceArea: "Commercial Litigation",
  model: "rel{AI}able Verifier v2.4",
  steps: [
    { t: "09:42:11", label: "Document uploaded" },
    { t: "09:42:14", label: "12 citations extracted" },
    { t: "09:42:38", label: "Authorities cross-checked against BAILII, ICLR, Westlaw UK" },
    { t: "09:43:02", label: "Contextual application analysed" },
    { t: "09:43:21", label: "Verification report generated" },
  ],
};
