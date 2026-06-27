import { useRef, useState } from "react";
import { Upload } from "lucide-react";

export function UploadZone({ onFile }: { onFile: (file: File) => void }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className={`group relative rounded-2xl border-2 border-dashed bg-card p-12 text-center shadow-elegant transition-all ${
        drag ? "border-brand bg-brand-soft/40" : "border-border hover:border-brand/50"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
      <button
        type="button"
        aria-label="Browse files"
        onClick={() => inputRef.current?.click()}
        className="mx-auto mb-5 flex h-24 w-24 cursor-pointer items-center justify-center rounded-2xl bg-brand-soft text-brand transition-all hover:bg-brand hover:text-primary-foreground hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
      >
        <Upload className="h-10 w-10" />
      </button>
      <h3 className="font-display text-2xl text-navy">
        Drag & drop your legal document here
      </h3>
      <p className="mt-2 text-sm text-muted-foreground">
        or browse from your device — PDF
      </p>
    </div>
  );
}
