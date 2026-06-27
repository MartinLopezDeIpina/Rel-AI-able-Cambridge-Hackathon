import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Moon, FileWarning, Download, Trash2 } from "lucide-react";
import { TopBar } from "@/components/relaiable/TopBar";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { SubpageFooter, GoBackButton } from "@/components/relaiable/SubpageChrome";
import {
  getValidationLog,
  getValidationLogCounts,
  clearValidationLog,
  subscribeValidationLog,
} from "@/lib/validation";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings — rel{AI}able" },
      { name: "description", content: "Manage your rel{AI}able workspace settings." },
    ],
  }),
  component: SettingsPage,
});

function useValidationLog(): string[] {
  return useSyncExternalStore(
    subscribeValidationLog,
    getValidationLog,
    getValidationLog,
  );
}

function SettingsPage() {
  const [dark, setDark] = useState(false);
  const log = useValidationLog();

  useEffect(() => {
    const stored = localStorage.getItem("relaiable-theme");
    const isDark = stored === "dark";
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  const toggle = (next: boolean) => {
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("relaiable-theme", next ? "dark" : "light");
  };

  const downloadLog = () => {
    const body = log.length > 0 ? log.join("\n") + "\n" : "";
    const blob = new Blob([body], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "validation_results.log";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex min-h-screen w-full flex-col bg-background">
      <TopBar />
      <main className="mx-auto w-full max-w-5xl px-4 py-8 md:px-6">
        <div className="mb-8">
          <h1 className="font-display text-4xl text-navy">Settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your workspace, appearance and account preferences.
          </p>
        </div>

        <Card className="mb-8 p-5">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
                <Moon className="h-5 w-5" />
              </span>
              <div>
                <p className="font-medium text-foreground">Dark mode</p>
                <p className="text-xs text-muted-foreground">
                  Switch the entire interface between light and dark theme.
                </p>
              </div>
            </div>
            <Switch checked={dark} onCheckedChange={toggle} aria-label="Toggle dark mode" />
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
                <FileWarning className="h-5 w-5" />
              </span>
              <div>
                <p className="font-medium text-foreground">Validation log</p>
                <p className="text-xs text-muted-foreground">
                  Records every <code>config.json</code> or <code>report.json</code> payload
                  that was rejected because required fields were missing or empty.
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Current entries: <span className="font-medium text-foreground">{log.length}</span>
                  {log.length > 0 && (() => {
                    const { errors, infos } = getValidationLogCounts();
                    return (
                      <span className="ml-1 text-muted-foreground">
                        ({errors} {errors === 1 ? "error" : "errors"} / {infos} {infos === 1 ? "info" : "infos"})
                      </span>
                    );
                  })()}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={downloadLog}
                disabled={log.length === 0}
              >
                <Download className="mr-1.5 h-4 w-4" />
                Download
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={clearValidationLog}
                disabled={log.length === 0}
              >
                <Trash2 className="mr-1.5 h-4 w-4" />
                Clear
              </Button>
            </div>
          </div>

          {log.length > 0 && (
            <pre className="mt-4 max-h-64 overflow-auto rounded-md border bg-muted/40 p-3 text-[11px] leading-relaxed text-muted-foreground">
              {log.join("\n")}
            </pre>
          )}
        </Card>
      </main>
      <SubpageFooter />
      <GoBackButton />
    </div>
  );
}
