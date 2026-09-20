export default function ConfidenceBadge({value, source}) {
  if (value === null || value === undefined) {
    return <span className="confidence-badge unavailable" title={source || 'confidence unavailable'}>Review Suggested</span>;
  }
  const label = value >= 90 ? 'High Confidence' : value >= 70 ? 'Check Recommended' : 'Review Suggested';
  const tone = value >= 90 ? 'high' : value >= 70 ? 'medium' : 'low';
  return <span className={`confidence-badge ${tone}`} title={source || 'recognition confidence'}>{label}</span>;
}
