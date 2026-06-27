import { create } from "zustand";
import type { Citation } from "./mock-citations";

interface AnalysisState {
  hasAnalysis: boolean;
  documentName: string | null;
  citations: Citation[]; // live verification result ([] => components fall back to mock)
  documentParagraphs: string[]; // live document-preview paragraphs
  jurisdiction: string;
  setJurisdiction: (j: string) => void;
  /** Store a real verification result (from POST /api/citations/verify). */
  setReport: (name: string, citations: Citation[], paragraphs?: string[]) => void;
  /** Seed the bundled demo (citations stay empty -> mock fallback renders). */
  startDemo: (name?: string) => void;
  reset: () => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  hasAnalysis: false,
  documentName: null,
  citations: [],
  documentParagraphs: [],
  jurisdiction: "England & Wales",
  setJurisdiction: (j) => set({ jurisdiction: j }),
  setReport: (name, citations, paragraphs = []) =>
    set({ hasAnalysis: true, documentName: name, citations, documentParagraphs: paragraphs }),
  startDemo: (name = "Demo — Halberd Trading v Orient Pacific.docx") =>
    set({ hasAnalysis: true, documentName: name, citations: [], documentParagraphs: [] }),
  reset: () =>
    set({ hasAnalysis: false, documentName: null, citations: [], documentParagraphs: [] }),
}));
