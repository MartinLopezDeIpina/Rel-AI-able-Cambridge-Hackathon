// Typed client for the backend citation-verification API + a mapper from the backend
// verify response to the UI's `Citation` shape.
import type { Citation, CitationStatus } from "./mock-citations";

/** One citation as returned by POST /api/citations/verify. */
export interface VerifyItem {
  id: number;
  citation_name: string;
  year: number | null;
  court: string | null;
  status:
    | "EXISTS_CORRECTLY_APPLIED"
    | "EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT"
    | "DOESNT_EXIST";
  confidence_score: number; // 0..1
  associate_claim: string;
  actual_holding: string;
  explanation: string;
  raw: string;
  needs_review: boolean;
  matched_source: string | null;
  match_method: string | null;
  used_semantic_fallback: boolean;
  field_mismatches: { field: string; citing_value: unknown; source_value: unknown }[];
  distortion: {
    classification: string;
    mischaracterised_pct: number;
    out_of_context_pct: number;
    plain_language_holding: string;
  } | null;
}

export interface VerifyResponse {
  citations: VerifyItem[];
  summary: {
    total: number;
    exists: number;
    doesnt_exist: number;
    needs_review: number;
    mischaracterised: number;
  };
}

const ENDPOINT = "/api/citations/verify";

export async function verifyFile(file: File): Promise<VerifyResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(ENDPOINT, { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function verifyText(text: string): Promise<VerifyResponse> {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body?.detail || `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

// ---- backend -> UI mapping ------------------------------------------------

function mapStatus(item: VerifyItem): CitationStatus {
  if (item.needs_review) return "review";
  switch (item.status) {
    case "EXISTS_CORRECTLY_APPLIED":
      return "verified";
    case "EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT":
      return "mischar";
    default:
      return "risk"; // DOESNT_EXIST
  }
}

const ISSUE: Record<CitationStatus, string> = {
  verified: "None",
  review: "Existence unconfirmed",
  mischar: "Application questioned",
  risk: "Authority cannot be located",
};

const ACTION: Record<CitationStatus, string> = {
  verified: "Retain",
  review: "Manual review",
  mischar: "Revise the proposition",
  risk: "Remove or re-verify",
};

export function toCitation(item: VerifyItem): Citation {
  const status = mapStatus(item);
  const mismatchFields = item.field_mismatches.map((m) => m.field).join(", ");
  const issue =
    status === "mischar" && mismatchFields
      ? `Application questioned · ${mismatchFields} differ`
      : ISSUE[status];
  return {
    id: String(item.id),
    caseName: item.citation_name,
    court: item.court ?? "—",
    year: item.year ?? 0,
    citation: item.raw,
    summary: item.explanation,
    status,
    confidence: Math.round((item.confidence_score ?? 0) * 100),
    holding: item.actual_holding || "Not available in the sources.",
    howUsed: item.associate_claim || "—",
    reasoning: item.explanation,
    recommendation: ACTION[status],
    supporting: item.matched_source ? `Matched source: ${item.matched_source}` : undefined,
    issue,
    action: ACTION[status],
    paragraph: 0, // set by toReport (document order)
  };
}

/** Map the whole response into the UI report (citations + a preview built from the
 *  associate claims, since we don't ship the raw document text to the client). */
export function toReport(resp: VerifyResponse): { citations: Citation[]; paragraphs: string[] } {
  const citations = resp.citations.map((item, idx) => ({
    ...toCitation(item),
    paragraph: idx,
  }));
  const paragraphs = citations.map(
    (c) => c.howUsed && c.howUsed !== "—" ? c.howUsed : `${c.caseName} ${c.citation}`,
  );
  return { citations, paragraphs };
}
