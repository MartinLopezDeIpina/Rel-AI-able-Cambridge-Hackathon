import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  X,
  Home,
  LayoutDashboard,
  Settings,
} from "lucide-react";
import { useDashboardOverlay } from "@/lib/dashboard-toggle";
import { Logo } from "./Logo";

const NAV_ITEMS = [
  { title: "Home", url: "/", icon: Home },
  { title: "Dashboard", url: "/dashboard", icon: LayoutDashboard },
  { title: "Settings", url: "/settings", icon: Settings },
] as const;


const PANEL_WIDTH = 320;

export function DashboardOverlay() {
  const open = useDashboardOverlay((s) => s.open);
  const close = useDashboardOverlay((s) => s.close);
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(open);

  useEffect(() => {
    if (open) {
      setMounted(true);
      // next frame -> slide in
      const id = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(id);
    }
    setVisible(false);
    const t = setTimeout(() => setMounted(false), 220);
    return () => clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  if (!mounted) return null;

  return (
    <>
      {/* Light backdrop to the right of the panel — click to close, page stays visible. */}
      <button
        aria-label="Close workspace navigation"
        onClick={close}
        className={`fixed inset-y-0 right-0 z-40 bg-black/20 transition-opacity duration-200 ${
          visible ? "opacity-100" : "opacity-0"
        }`}
        style={{ left: PANEL_WIDTH }}
      />
      <aside
        aria-label="Workspace navigation"
        className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r bg-background shadow-lift transition-transform duration-200 ease-out ${
          visible ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ width: PANEL_WIDTH, maxWidth: "92vw" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-4">
          <Logo />
          <button
            onClick={close}
            aria-label="Close workspace navigation"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border bg-card text-slate-ink shadow-elegant transition hover:text-navy"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-auto p-3">
          <div className="px-2 pb-2 text-xs font-medium uppercase tracking-wide text-slate-ink/70">
            Workspace
          </div>
          <ul className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <li key={item.title}>
                <Link
                  to={item.url}
                  onClick={close}
                  className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-foreground transition hover:bg-muted"
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
    </>
  );
}
