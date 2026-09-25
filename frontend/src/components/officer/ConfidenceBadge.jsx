export default function ConfidenceBadge({value}) {
  if (value === null || value === undefined) {
    return <span className="confidence-badge unavailable">Evidence unavailable</span>;
  }
  const label = value >= 85 ? 'HIGH' : value >= 65 ? 'MEDIUM' : 'LOW';
  const tone = value >= 85 ? 'high' : value >= 65 ? 'medium' : 'low';
  return <span className={`confidence-badge ${tone}`} title="Recognition evidence combines OCR/HTR confidence, repeated-read stability, and agreement between recognition methods. It is not a probability of correctness.">{label} · {Math.round(value)}%</span>;
}

export function ValidationBadge({validation}) {
  const status = validation?.status || 'UNAVAILABLE';
  const tone = status === 'PASS' ? 'high' : status === 'NEEDS_REVIEW' ? 'medium' : 'unavailable';
  return <span className={`confidence-badge validation-badge ${tone}`} title="Validation checks field format and structure separately from recognition evidence.">Validation: {status.replace('_', ' ')}</span>;
}
