import { FootballShell } from "@/components/football-shell";
import { PlayerDevelopmentView } from "@/components/player-development-view";

export default function PlayerDevelopmentPage() {
  return (
    <FootballShell activePage="player-development">
      <PlayerDevelopmentView />
    </FootballShell>
  );
}
