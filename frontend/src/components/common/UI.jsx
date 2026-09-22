'use client';

export function StatusBadge({status}) {
  const key = (status || '').toLowerCase().replaceAll('_', '-');
  return <span className={`status ${key}`}>{(status || 'Unknown').replaceAll('_', ' ')}</span>;
}

export function Loader({label = 'Loading data…'}) {
  return <div className="loader" role="status" aria-live="polite"><span aria-hidden="true" />{label}</div>;
}

export function Empty({title, text}) {
  return <div className="empty"><div className="empty-icon" aria-hidden="true">⌂</div><h3>{title}</h3><p>{text}</p></div>;
}

export function ErrorMessage({children}) {
  return children ? <div className="error" role="alert">{children}</div> : null;
}

export function Toast({message, tone = 'success', onDismiss}) {
  if (!message) return null;
  return <div className={`toast ${tone}`} role={tone === 'error' ? 'alert' : 'status'} aria-live="polite">
    <span>{message}</span>
    <button type="button" onClick={onDismiss} aria-label="Dismiss message">×</button>
  </div>;
}

export function Button({children, variant = '', loading, loadingText = 'Working…', ...props}) {
  const {disabled, ...buttonProps} = props;
  return <button {...buttonProps} className={`button ${variant}`} aria-busy={Boolean(loading)} disabled={loading || disabled}>
    {loading ? loadingText : children}
  </button>;
}
