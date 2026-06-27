// Single source of truth for the dashboard/report data: the live verification result
// from the store, falling back to the bundled mock so the demo + direct navigation
// keep working before any upload.
import { useAnalysisStore } from "./analysis-store";
import {
  MOCK_CITATIONS,
  MOCK_DOCUMENT,
  MOCK_DOC_PARAGRAPHS,
  type Citation,
  type CitationStatus,
} from "./mock-citations";

const STATUS_PRIORITY: Record<CitationStatus, number> = {
  risk: 0,
  mischar: 1,
  review: 2,
  verified: 3,
};

export function sortCitations(citations: Citation[]): Citation[] {
  return [...citations].sort((a, b) => {
    const d = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
    return d !== 0 ? d : a.confidence - b.confidence;
  });
}

export interface Report {
  citations: Citation[]; // document order
  sorted: Citation[]; // by status severity (table/report order)
  paragraphs: string[]; // document preview paragraphs
  document: typeof MOCK_DOCUMENT;
  isLive: boolean;
}

/** Live report from the store, or the bundled mock when nothing has been analysed. */
export function useReport(): Report {
  // Live verification result comes from the polled report.json (store.report);
  // fall back to the bundled mock until an analysis has completed.
  const report = useAnalysisStore((s) => s.report);
  const documentName = useAnalysisStore((s) => s.documentName);
  const citations = report?.citations ?? [];
  const isLive = citations.length > 0;

  if (!isLive) {
    return {
      citations: MOCK_CITATIONS,
      sorted: sortCitations(MOCK_CITATIONS),
      paragraphs: MOCK_DOC_PARAGRAPHS,
      document: MOCK_DOCUMENT,
      isLive: false,
    };
  }
  return {
    citations,
    sorted: sortCitations(citations),
    // The store doesn't carry per-document paragraphs yet; show the sample preview.
    paragraphs: MOCK_DOC_PARAGRAPHS,
    document: { ...MOCK_DOCUMENT, name: documentName ?? MOCK_DOCUMENT.name },
    isLive: true,
  };
}
