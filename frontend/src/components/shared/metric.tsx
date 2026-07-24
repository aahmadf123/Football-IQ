/**
 * Shared metric primitives (previously copy-pasted across page views).
 *
 * `Metric` is the boxed stat card (label / big value / optional unit);
 * `MetricLine` is the compact label–value row used inside list stacks.
 */

export function Metric({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit?: string;
}) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {unit ? <small>{unit}</small> : null}
    </div>
  );
}

export function MetricLine({
  label,
  value,
  style,
}: {
  label: string;
  value: string;
  style?: React.CSSProperties;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, ...style }}>
      <span className="small-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
