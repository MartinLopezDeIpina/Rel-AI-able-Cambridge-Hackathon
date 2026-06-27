import { ShieldCheck } from "lucide-react";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-md bg-navy text-primary-foreground">
        <ShieldCheck className="h-4 w-4" strokeWidth={2.2} />
        <span className="absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-brand ring-2 ring-background" />
      </span>
      <span className="font-display text-xl tracking-tight text-navy">
        rel<span className="text-brand">{"{AI}"}</span>able
      </span>
    </div>
  );
}
