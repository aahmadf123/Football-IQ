/**
 * SVG polyline trend chart. Renders whatever numeric series it is given and an
 * honest "not available" box when there is none — callers must never feed it
 * fabricated data.
 */

export function TrendLine({ data }: { data: number[] | undefined }) {
  if (!data || data.length === 0) {
    return (
      <div className="chart-box" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span className="kicker">Trend not available</span>
      </div>
    );
  }
  const points = data.map((value, index) => `${(index / Math.max(data.length - 1, 1)) * 100},${100 - value}`).join(" ");
  return (
    <div className="chart-box">
      <svg viewBox="0 0 100 100" role="img" aria-label="Trend chart" style={{ width: "100%", height: "100%" }}>
        <polyline points={points} fill="none" stroke="var(--blue)" strokeWidth="3" vectorEffect="non-scaling-stroke" />
        {data.map((value, index) => (
          <circle key={index} cx={(index / Math.max(data.length - 1, 1)) * 100} cy={100 - value} r="2.2" fill="var(--gold)" />
        ))}
      </svg>
    </div>
  );
}
