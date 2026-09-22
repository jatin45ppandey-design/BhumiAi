'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {AlertTriangle, CheckCircle, Inbox, XCircle} from 'lucide-react';
import {api} from '../../lib/api';
import StatCard from '../../components/dashboard/StatCard';
import {Empty, ErrorMessage, Loader, StatusBadge} from '../../components/common/UI';

function QueueSection({title, eyebrow, rows, emptyTitle, emptyText}) {
  return <section className="card dashboard-attention" style={{marginTop: 18}}>
    <div className="section-head"><div><div className="eyebrow">{eyebrow}</div><h3>{title}</h3></div></div>
    {!rows.length ? <Empty title={emptyTitle} text={emptyText}/> : <div className="table-wrap"><table className="data-table"><thead><tr><th>RECORD</th><th>CITIZEN</th><th>LOCATION</th><th>RECEIVED</th><th>STATUS</th><th/></tr></thead><tbody>{rows.slice(0, 5).map(row => <tr key={row.id}>
      <td><b>#{row.id}</b><br/><small>{row.document?.original_filename || 'Land record'}</small></td>
      <td>{row.user?.name || '—'}</td><td>{[row.document?.village, row.document?.district].filter(Boolean).join(', ') || '—'}</td>
      <td>{new Date(row.submitted_at).toLocaleString()}</td><td><StatusBadge status={row.status}/></td>
      <td><Link className="button secondary" href={`/officer/review/${row.document_id}`}>Open review</Link></td>
    </tr>)}</tbody></table></div>}
  </section>;
}

export default function OfficerDashboard() {
  const [stats, setStats] = useState(null);
  const [submitted, setSubmitted] = useState([]);
  const [needsReview, setNeedsReview] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.officerDashboard(), api.submissions({status: 'SUBMITTED'}), api.submissions({status: 'NEEDS_REVIEW'})])
      .then(([dashboard, pendingRows, reviewRows]) => {
        setStats(dashboard); setSubmitted(pendingRows); setNeedsReview(reviewRows);
      }).catch(loadError => setError(loadError.message));
  }, []);

  if (!stats) return error ? <ErrorMessage>{error}</ErrorMessage> : <Loader label="Preparing today's work queue…"/>;
  return <>
    <div className="page-title officer-page-title"><div><div className="eyebrow">OFFICER WORKSPACE</div><h2>Verification work, prioritized.</h2><p>Start with records that need a decision, then keep the verified repository current.</p></div>{submitted.length ? <Link className="button" href="/officer/submissions?status=SUBMITTED"><Inbox size={16}/> Review next record</Link> : <button className="button" type="button" disabled><Inbox size={16}/> Review next record</button>}</div>
    <ErrorMessage>{error}</ErrorMessage>
    <div className="stat-grid officer-stat-grid">
      <StatCard label="Pending review" value={stats.pending} icon={Inbox}/>
      <StatCard label="Needs attention" value={stats.needs_review} icon={AlertTriangle} tone="amber" href="/officer/submissions?status=NEEDS_REVIEW"/>
      <StatCard label="Rejected" value={stats.rejected} icon={XCircle} tone="red" href="/officer/submissions?status=REJECTED"/>
      <StatCard label="Verified records" value={stats.verified} icon={CheckCircle} tone="green" href="/officer/records"/>
    </div>
    <QueueSection title="Needs your attention" eyebrow="ACTION REQUIRED" rows={needsReview} emptyTitle="No records waiting for attention" emptyText="Records needing further review will appear here."/>
    {submitted.length ? <QueueSection title="Pending review" eyebrow="NEW SUBMISSIONS" rows={submitted} emptyTitle="No records waiting for review" emptyText="New submissions will appear here automatically."/> : null}
  </>;
}
