'use client';

import { AlertTriangle, CheckCircle2, CircleDot, FileText, LoaderCircle, XCircle } from 'lucide-react';

export function StatusBadge({status}) {
  const key = (status || '').toLowerCase().replaceAll('_', '-');
  const label = (status || 'Unknown').replaceAll('_', ' ');
  const Icon = key === 'verified' ? CheckCircle2 : key === 'rejected' || key === 'failed' || key === 'error' ? XCircle : key === 'needs-review' || key === 'under-review' ? AlertTriangle : key === 'processing' ? LoaderCircle : CircleDot;
  return <span className={`status ${key}`}><Icon aria-hidden="true" size={12} />{label}</span>;
}

export function Loader({label = 'Loading data…'}) {
  return <div className="loader" role="status" aria-live="polite"><span aria-hidden="true" />{label}</div>;
}

export function RouteSkeleton({variant = 'page'}) {
  return <div className={`route-skeleton route-skeleton-${variant}`} role="status" aria-live="polite" aria-label="Loading page">
    <div className="skeleton-heading"><span className="skeleton-block skeleton-eyebrow"/><span className="skeleton-block skeleton-title"/><span className="skeleton-block skeleton-copy"/></div>
    {variant === 'dashboard' && <div className="skeleton-stats">{[1, 2, 3, 4].map(item => <span className="skeleton-block skeleton-stat" key={item}/>)}</div>}
    {variant === 'workspace' ? <div className="skeleton-workbench"><span className="skeleton-block skeleton-pane"/><span className="skeleton-block skeleton-pane"/></div> : <div className="skeleton-panel"><span className="skeleton-block skeleton-panel-head"/>{[1, 2, 3, 4, 5].map(item => <span className="skeleton-block skeleton-row" key={item}/>)}</div>}
  </div>;
}

export function Empty({title, text}) {
  return <div className="empty"><div className="empty-icon" aria-hidden="true"><FileText size={21}/></div><h3>{title}</h3><p>{text}</p></div>;
}

export function ErrorMessage({children}) {
  return children ? <div className="error" role="alert">{children}</div> : null;
}

export function Toast({message, tone = 'success', onDismiss}) {
  if (!message) return null;
  return <div className={`toast ${tone}`} role={tone === 'error' ? 'alert' : 'status'} aria-live="polite"><span>{message}</span><button type="button" onClick={onDismiss} aria-label="Dismiss message">×</button></div>;
}

export function Button({children, variant = '', loading, loadingText = 'Working…', ...props}) {
  const {disabled, ...buttonProps} = props;
  return <button {...buttonProps} className={`button ${variant}`} aria-busy={Boolean(loading)} disabled={loading || disabled}>{loading ? loadingText : children}</button>;
}
