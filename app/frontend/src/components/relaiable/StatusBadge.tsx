import { CheckCircle2, AlertTriangle, AlertOctagon, XCircle } from "lucide-react";
import type { CitationStatus } from "@/lib/mock-citations";
import { STATUS_META } from "@/lib/mock-citations";

const ICONS = {
  verified: CheckCircle2,
  review: AlertTriangle,
  mischar: AlertOctagon,
  risk: XCircle,
};

const STYLES: Record<CitationStatus, string> = {
  verified: "bg-verified/10 text-verified ring-verified/20",
  review: "bg-review/15 text-[color:oklch(0.45_0.12_85)] ring-review/30",
  mischar: "bg-mischar/10 text-mischar ring-mischar/25",
  risk: "bg-risk/10 text-risk ring-risk/25",
};

export function StatusBadge({
  status,
  size = "sm",
}: {
  status: CitationStatus;
  size?: "sm" | "md";
}) {
  const Icon = ICONS[status];
  const label = STATUS_META[status].label;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${STYLES[status]} ${
        size === "md" ? "text-sm px-3 py-1.5" : ""
      }`}
    >
      <Icon className={size === "md" ? "h-4 w-4" : "h-3.5 w-3.5"} strokeWidth={2.2} />
      {label}
    </span>
  );
}
