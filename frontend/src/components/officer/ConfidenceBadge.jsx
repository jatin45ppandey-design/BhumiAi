export default function ConfidenceBadge({value, source}) {
  if (value === null || value === undefined) {
    return <span className="confidence-badge unavailable">Confidence unavailable · Review suggested</span>;
  }
  const label = value >= 90 ? 'High' : value >= 70 ? 'Medium' : 'Low';
  const tone = value >= 90 ? 'high' : value >= 70 ? 'medium' : 'low';
  return <span className={`confidence-badge ${tone}`}>Confidence: {label} ({Math.round(value)}%)<small className="developer-only">{source || 'Recognition confidence'}</small></span>;
}
