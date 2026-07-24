import { FootballShell } from "@/components/football-shell";
import { PlayersView } from "@/components/players-view";

export default function PlayersPage() {
  return (
    <FootballShell activePage="players">
      <PlayersView />
    </FootballShell>
  );
}
