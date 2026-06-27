import { useEffect, useRef } from "react";
import { useRouterState } from "@tanstack/react-router";
import {
  MOCK_CITATIONS,
  MOCK_DOCUMENT,
  type Citation,
  type CitationStatus,
} from "@/lib/mock-citations";
import { useAnalysisStore } from "@/lib/analysis-store";

export type ReportStatus = "pending" | "complete";

export interface ReportPayload {
  status: ReportStatus;
  citations: Citation[];
}

export type DocumentConfig = typeof MOCK_DOCUMENT;

const FALLBACK_REPORT: ReportPayload = {
  status: "complete",
  citations: MOCK_CITATIONS,
};

export async function fetchReport(): Promise<ReportPayload> {
  try {
    const res = await fetch(`/report.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`report.json ${res.status}`);
    const data = (await res.json()) as ReportPayload;
    if (!data || !Array.isArray(data.citations)) throw new Error("malformed report.json");
    return { status: data.status === "pending" ? "pending" : "complete", citations: data.citations };
  } catch (err) {
    console.warn("[live-data] fetchReport fallback:", err);
    return FALLBACK_REPORT;
  }
}

export async function fetchConfig(): Promise<DocumentConfig> {
  try {
    const res = await fetch(`/config.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`config.json ${res.status}`);
    const data = (await res.json()) as DocumentConfig;
    if (!data || !data.name) throw new Error("malformed config.json");
    return data;
  } catch (err) {
    console.warn("[live-data] fetchConfig fallback:", err);
    return MOCK_DOCUMENT;
  }
}

const STATUS_PRIORITY: Record<CitationStatus, number> = {
  risk: 0,
  mischar: 1,
  review: 2,
  verified: 3,
};

export function sortCitations(list: Citation[]): Citation[] {
  return [...list].sort((a, b) => {
    const d = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
    if (d !== 0) return d;
    return a.confidence - b.confidence;
  });
}

// ---------- Hooks ----------

export function useLiveCitations(): Citation[] {
  return useAnalysisStore((s) => s.report?.citations ?? MOCK_CITATIONS);
}

export function useLiveSortedCitations(): Citation[] {
  const citations = useLiveCitations();
  return sortCitations(citations);
}

export function useLiveDocument(): DocumentConfig {
  return useAnalysisStore((s) => s.config ?? MOCK_DOCUMENT);
}

export function useReportStatus(): ReportStatus | null {
  return useAnalysisStore((s) => s.report?.status ?? null);
}

/**
 * Global hook: refetches config.json on every route change and on every
 * button/link click anywhere in the app (debounced).
 */
export function useConfigRefetch() {
  const loadConfig = useAnalysisStore((s) => s.loadConfig);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const timer = useRef<number | null>(null);

  // On mount + on every navigation
  useEffect(() => {
    void loadConfig();
  }, [pathname, loadConfig]);

  // On every button / link click anywhere
  useEffect(() => {
    const handler = (e: Event) => {
      const target = e.target as HTMLElement | null;
      if (!target || !target.closest) return;
      if (!target.closest('button, a, [role="button"]')) return;
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => {
        void loadConfig();
      }, 200);
    };
    document.addEventListener("click", handler, true);
    return () => {
      document.removeEventListener("click", handler, true);
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [loadConfig]);
}
