import { FootballShell } from "@/components/football-shell";
import { HealthWorkloadView } from "@/components/health-workload-view";

export default function HealthWorkloadPage() {
  return (
    <FootballShell activePage="health-workload">
      <HealthWorkloadView />
    </FootballShell>
  );
}
