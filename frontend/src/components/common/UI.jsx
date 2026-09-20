'use client';
export function StatusBadge({status}) { const key=(status||'').toLowerCase().replaceAll('_','-'); return <span className={`status ${key}`}>{(status||'Unknown').replaceAll('_',' ')}</span>; }
export function Loader({label='Loading data…'}) { return <div className="loader"><span></span>{label}</div>; }
export function Empty({title, text}) { return <div className="empty"><div className="empty-icon">⌁</div><h3>{title}</h3><p>{text}</p></div>; }
export function ErrorMessage({children}) { return children ? <div className="error">{children}</div> : null; }
export function Button({children, variant='', loading, ...props}) { return <button className={`button ${variant}`} disabled={loading || props.disabled} {...props}>{loading ? 'Working…' : children}</button>; }
