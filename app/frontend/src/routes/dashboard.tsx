import { createFileRoute } from "@tanstack/react-router";
import { DashboardWorkspace } from "@/components/relaiable/DashboardWorkspace";

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — rel{AI}able" },
      { name: "description", content: "Citation verification dashboard." },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  return <DashboardWorkspace />;
}
