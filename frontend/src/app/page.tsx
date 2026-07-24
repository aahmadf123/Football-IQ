import { FootballShell } from "@/components/football-shell";
import { DashboardView } from "@/components/dashboard-view";

export default function DashboardPage() {
  return (
    <FootballShell activePage="dashboard">
      <DashboardView />
    </FootballShell>
  );
}
