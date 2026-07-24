/**
 * Run/pass tendency table shared by the analytics and scouting surfaces.
 * Renders grouping key, play count, and a run-rate bar per entry.
 */

import type { TendencyEntry } from "@/lib/types";

export function TendencyTable({ entries }: { entries: TendencyEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="kicker">No tendencies above the minimum-sample threshold.</p>
    );
  }
  return (
    <div className="list-stack" style={{ gap: 4 }}>
      {entries.map((e) => (
        <div
          key={e.grouping_key}
          className="status-row"
          style={{ gridTemplateColumns: "1fr 56px minmax(90px, 1fr)" }}
        >
          <strong>{e.grouping_key}</strong>
          <span>{e.total_plays}</span>
          <div className="progress">
            <i style={{ "--value": `${Math.round(e.run_rate * 100)}%` } as React.CSSProperties} />
          </div>
        </div>
      ))}
    </div>
  );
}
