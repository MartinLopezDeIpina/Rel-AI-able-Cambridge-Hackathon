import { useRef, useState } from "react";
import { Upload, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";

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
        accept=".pdf,.docx,.doc,.txt"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
      <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-xl bg-brand-soft text-brand">
        <Upload className="h-6 w-6" />
      </div>
      <h3 className="font-display text-2xl text-navy">
        Drag & drop your legal document here
      </h3>
      <p className="mt-2 text-sm text-muted-foreground">
        or browse from your device — PDF, DOCX, DOC, TXT
      </p>
      <div className="mt-6 flex items-center justify-center gap-3">
        <Button
          size="lg"
          className="bg-navy text-primary-foreground hover:bg-navy-soft"
          onClick={() => inputRef.current?.click()}
        >
          <FileText className="mr-2 h-4 w-4" /> Browse Files
        </Button>
      </div>
    </div>
  );
}
