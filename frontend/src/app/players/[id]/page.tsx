import { footballData } from "@/lib/mock-data";
import { PlayerProfileClient } from "./player-profile-client";

export function generateStaticParams() {
  return footballData.players.map((p) => ({ id: p.id }));
}

export default async function PlayerProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PlayerProfileClient id={decodeURIComponent(id)} />;
}
