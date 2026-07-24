import { FootballShell } from "@/components/football-shell";
import { ReportsView } from "@/components/reports-view";

export default function ReportsPage() {
  return (
    <FootballShell activePage="reports">
      <ReportsView />
    </FootballShell>
  );
}
