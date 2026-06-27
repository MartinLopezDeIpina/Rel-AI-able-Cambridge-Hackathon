// Validation for config.json and report.json.
// - Empty strings, null, undefined, [] count as missing.
// - 0 and false do NOT count as missing.
// - Failures are appended to an in-memory log, downloadable from Settings.

import type { Citation } from "@/lib/mock-citations";

export type ReportStatus = "pending" | "complete";
export interface ReportPayload {
  status: ReportStatus;
  citations: Citation[];
}
export interface DocumentConfig {
  name: string;
  uploadedAt: string;
  jurisdiction: string;
  practiceArea: string;
  model: string;
  steps: Array<{ t: string; label: string }>;
}

export interface ValidationResult<T> {
  valid: boolean;
  data?: T;
  missing: string[];
}

export function isMissing(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === "string" && v === "") return true;
  if (Array.isArray(v) && v.length === 0) return true;
  return false;
}

function isNonEmptyString(v: unknown): v is string {
  return typeof v === "string" && v !== "";
}

const CITATION_STATUSES = new Set(["verified", "review", "mischar", "risk"]);
const ID_RE = /^c\d+$/;

// ---------- config.json ----------

export function validateConfig(raw: unknown): ValidationResult<DocumentConfig> {
  const missing: string[] = [];
  const obj = (raw ?? {}) as Record<string, unknown>;

  const stringFields = ["name", "uploadedAt", "jurisdiction", "practiceArea", "model"] as const;
  for (const f of stringFields) {
    if (!isNonEmptyString(obj[f])) missing.push(f);
  }

  const steps = obj.steps;
  if (!Array.isArray(steps) || steps.length === 0) {
    missing.push("steps");
  } else {
    steps.forEach((s, i) => {
      const step = (s ?? {}) as Record<string, unknown>;
      if (!isNonEmptyString(step.t)) missing.push(`steps[${i}].t`);
      if (!isNonEmptyString(step.label)) missing.push(`steps[${i}].label`);
    });
  }

  if (missing.length > 0) return { valid: false, missing };
  return { valid: true, data: raw as DocumentConfig, missing: [] };
}

// ---------- report.json ----------

export function validateReport(raw: unknown): ValidationResult<ReportPayload> {
  const missing: string[] = [];
  const obj = (raw ?? {}) as Record<string, unknown>;

  const status = obj.status;
  if (status !== "pending" && status !== "complete") {
    missing.push("status (invalid value)");
  }

  const citations = obj.citations;
  if (!Array.isArray(citations)) {
    missing.push("citations");
  } else if (status === "complete" && citations.length === 0) {
    missing.push("citations (empty while status=complete)");
  } else {
    citations.forEach((c, i) => {
      const cit = (c ?? {}) as Record<string, unknown>;

      if (!isNonEmptyString(cit.id)) {
        missing.push(`citations[${i}].id`);
      } else if (!ID_RE.test(cit.id as string)) {
        missing.push(`citations[${i}].id (invalid format)`);
      }

      if (!isNonEmptyString(cit.caseName)) missing.push(`citations[${i}].caseName`);
      if (!isNonEmptyString(cit.court)) missing.push(`citations[${i}].court`);
      if (!isNonEmptyString(cit.citation)) missing.push(`citations[${i}].citation`);

      if (typeof cit.year !== "number" || Number.isNaN(cit.year)) {
        missing.push(`citations[${i}].year`);
      }

      if (!isNonEmptyString(cit.status)) {
        missing.push(`citations[${i}].status`);
      } else if (!CITATION_STATUSES.has(cit.status as string)) {
        missing.push(`citations[${i}].status (invalid value)`);
      }

      // confidence: 0 IS valid; strict: must be a finite number in [0, 100].
      const conf = cit.confidence;
      if (typeof conf !== "number" || !Number.isFinite(conf)) {
        missing.push(`citations[${i}].confidence (invalid value: ${JSON.stringify(conf)})`);
      } else if (conf < 0 || conf > 100) {
        missing.push(`citations[${i}].confidence (out of range: ${conf})`);
      }
    });
  }

  if (missing.length > 0) return { valid: false, missing };
  return { valid: true, data: raw as ReportPayload, missing: [] };
}

// ---------- In-memory log ----------

export type LogLevel = "info" | "error";
interface LogEntry {
  level: LogLevel;
  line: string;
}

const log: LogEntry[] = [];
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function formatEntry(entry: LogEntry): string {
  const prefix = entry.level === "info" ? "[INFO] " : "[ERROR]";
  return `${prefix} ${entry.line}`;
}

export function appendValidationLog(source: string, missing: string[]): void {
  const ts = new Date().toISOString();
  const line =
    missing.length > 0
      ? `[${ts}] ${source} — missing/empty fields: ${missing.join(", ")}`
      : `[${ts}] ${source} — ok`;
  log.push({ level: "error", line });
  // eslint-disable-next-line no-console
  console.warn("[validation]", line);
  emit();
}

export function logInfo(source: string, message: string): void {
  const ts = new Date().toISOString();
  const line = `[${ts}] ${source} — ${message}`;
  log.push({ level: "info", line });
  // eslint-disable-next-line no-console
  console.info("[validation]", line);
  emit();
}

export function getValidationLog(): string[] {
  return log.map(formatEntry);
}

export function getValidationLogCounts(): { errors: number; infos: number } {
  let errors = 0;
  let infos = 0;
  for (const e of log) {
    if (e.level === "error") errors++;
    else infos++;
  }
  return { errors, infos };
}

export function clearValidationLog(): void {
  log.length = 0;
  emit();
}

export function subscribeValidationLog(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
