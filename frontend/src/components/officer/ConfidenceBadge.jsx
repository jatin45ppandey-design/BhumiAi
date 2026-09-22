export default function ConfidenceBadge({value, source}) {
  if (value === null || value === undefined) {
    return <span className="confidence-badge unavailable">Recognition confidence unavailable · Review suggested</span>;
  }
  const label = value >= 90 ? 'High' : value >= 70 ? 'Medium' : 'Low';
  const tone = value >= 90 ? 'high' : value >= 70 ? 'medium' : 'low';
  return <span className={`confidence-badge ${tone}`} title="Recognition confidence supports review; it is not a guarantee of correctness.">Recognition confidence · {label} · {Math.round(value)}%<small className="developer-only">{source || 'Recognition confidence'}</small></span>;
}
