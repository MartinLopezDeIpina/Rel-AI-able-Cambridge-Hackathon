import { create } from "zustand";

interface AnalysisState {
  hasAnalysis: boolean;
  documentName: string | null;
  jurisdiction: string;
  setJurisdiction: (j: string) => void;
  startAnalysis: (name: string) => void;
  reset: () => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  hasAnalysis: false,
  documentName: null,
  jurisdiction: "England & Wales",
  setJurisdiction: (j) => set({ jurisdiction: j }),
  startAnalysis: (name) => set({ hasAnalysis: true, documentName: name }),
  reset: () => set({ hasAnalysis: false, documentName: null }),
}));
