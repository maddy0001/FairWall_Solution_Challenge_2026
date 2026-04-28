import { createFileRoute } from "@tanstack/react-router";
import { FairWallDashboard } from "@/components/fairwall/FairWallDashboard";

export const Route = createFileRoute("/")({
  component: Index,
  head: () => ({
    meta: [
      { title: "FairWall — AI Fairness Firewall Dashboard" },
      { name: "description", content: "Real-time AI bias monitoring, intervention tracking, and fairness scoring dashboard." },
    ],
  }),
});

function Index() {
  return <FairWallDashboard />;
}
