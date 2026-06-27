import { create } from "zustand";
import { MOCK_DOCUMENT, type Citation } from "@/lib/mock-citations";
import {
  validateConfig,
  validateReport,
  appendValidationLog,
  logInfo,
} from "@/lib/validation";

export type ReportStatus = "pending" | "complete";

export interface ReportPayload {
  status: ReportStatus;
  citations: Citation[];
}

export type DocumentConfig = typeof MOCK_DOCUMENT;

// Dedupe flag: one "report not ready" info per polling session.
let reportNotReadyLogged = false;

interface AnalysisState {
  hasAnalysis: boolean;
  documentName: string | null;
  jurisdiction: string;
  report: ReportPayload | null;
  config: DocumentConfig | null;
  _pollTimer: number | null;
  setJurisdiction: (j: string) => void;
  startAnalysis: (name: string) => void;
  reset: () => void;
  loadReport: () => Promise<void>;
  loadConfig: () => Promise<void>;
  startReportPolling: () => void;
  stopReportPolling: () => void;
}

/**
 * Fetch + validate report.json.
 * Returns the validated payload, or null when:
 *   - the file is not yet available (404) — logged once as INFO, polling continues
 *   - network/parse/validation error — logged as ERROR, caller keeps existing value
 */
async function fetchValidatedReport(): Promise<ReportPayload | null> {
  let raw: unknown;
  try {
    const res = await fetch(`/report.json?t=${Date.now()}`, { cache: "no-store" });
    if (res.status === 404) {
      if (!reportNotReadyLogged) {
        logInfo("report.json", "404 – report not ready yet (polling continues)");
        reportNotReadyLogged = true;
      }
      return null;
    }
    if (!res.ok) {
      appendValidationLog("report.json", [`HTTP ${res.status}`]);
      return null;
    }
    raw = await res.json();
  } catch (err) {
    if (err instanceof SyntaxError) {
      appendValidationLog("report.json (parse error)", [String(err.message)]);
    }
    return null;
  }
  const result = validateReport(raw);
  if (!result.valid) {
    appendValidationLog("report.json", result.missing);
    return null;
  }
  // Successful load → reset dedupe so a later 404 (new analysis) is logged again.
  reportNotReadyLogged = false;
  return result.data!;
}

async function fetchValidatedConfig(): Promise<DocumentConfig | null> {
  let raw: unknown;
  try {
    const res = await fetch(`/config.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) return null;
    raw = await res.json();
  } catch (err) {
    if (err instanceof SyntaxError) {
      appendValidationLog("config.json (parse error)", [String(err.message)]);
    }
    return null;
  }
  const result = validateConfig(raw);
  if (!result.valid) {
    appendValidationLog("config.json", result.missing);
    return null;
  }
  return result.data as DocumentConfig;
}

export const useAnalysisStore = create<AnalysisState>((set, get) => ({
  hasAnalysis: false,
  documentName: null,
  jurisdiction: "UK",
  report: null,
  config: null,
  _pollTimer: null,
  setJurisdiction: (j) => set({ jurisdiction: j }),
  startAnalysis: (name) => set({ hasAnalysis: true, documentName: name }),
  reset: () => {
    get().stopReportPolling();
    reportNotReadyLogged = false;
    set({ hasAnalysis: false, documentName: null, report: null });
  },
  loadReport: async () => {
    const report = await fetchValidatedReport();
    if (report) {
      set({ report });
      if (report.status === "complete") get().stopReportPolling();
    }
    // else: keep existing store value, polling continues
  },
  loadConfig: async () => {
    const config = await fetchValidatedConfig();
    if (config) {
      set({ config });
    } else if (get().config === null) {
      // Initial fallback so the UI has something to render.
      set({ config: MOCK_DOCUMENT });
    }
  },
  startReportPolling: () => {
    get().stopReportPolling();
    void get().loadReport();
    const id = window.setInterval(() => {
      void get().loadReport();
    }, 1500);
    set({ _pollTimer: id });
  },
  stopReportPolling: () => {
    const t = get()._pollTimer;
    if (t !== null) {
      window.clearInterval(t);
      set({ _pollTimer: null });
    }
  },
}));

