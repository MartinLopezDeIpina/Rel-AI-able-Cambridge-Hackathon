import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "./StatusBadge";

import { type Citation } from "@/lib/mock-citations";
import { useLiveCitations, useLiveSortedCitations } from "@/lib/live-data";
import { ArrowUpRight } from "lucide-react";

export function CitationTable({ onOpen }: { onOpen: (c: Citation) => void }) {
  const citations = useLiveCitations();
  const sorted = useLiveSortedCitations();
  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-elegant">
      <div className="flex items-center justify-between border-b px-5 py-4">
        <div>
          <h3 className="font-display text-lg text-navy">All citations</h3>
          <p className="text-xs text-muted-foreground">
            Click a row to open the full analysis.
          </p>
        </div>
        <span className="rounded-full bg-muted px-3 py-1 text-xs text-slate-ink">
          {citations.length} citations
        </span>
      </div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Citation</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Issue</TableHead>
            <TableHead className="w-8" />

          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((c) => (
            <TableRow
              key={c.id}
              onClick={() => onOpen(c)}
              className="cursor-pointer"
            >
              <TableCell>
                <div className="font-medium text-navy">{c.caseName}</div>
                <div className="font-mono text-xs text-muted-foreground">{c.citation}</div>
              </TableCell>
              <TableCell><StatusBadge status={c.status} /></TableCell>
              
              <TableCell className="text-sm text-slate-ink">{c.issue}</TableCell>
              <TableCell>

                <ArrowUpRight className="h-4 w-4 text-muted-foreground" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
