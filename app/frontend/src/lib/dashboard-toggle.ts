import { create } from "zustand";

type DashboardOverlayState = {
  open: boolean;
  toggle: () => void;
  close: () => void;
  openOverlay: () => void;
};

export const useDashboardOverlay = create<DashboardOverlayState>((set) => ({
  open: false,
  toggle: () => set((s) => ({ open: !s.open })),
  close: () => set({ open: false }),
  openOverlay: () => set({ open: true }),
}));

// Back-compat shim for any lingering callers.
export function toggleDashboard() {
  useDashboardOverlay.getState().toggle();
}
