'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {Activity, AlertTriangle, ArrowRight, CheckCircle, ClipboardCheck, FileSearch, Inbox, ListFilter, XCircle} from 'lucide-react';
import {api} from '../../lib/api';
import {activityDescription, activityLabel, isWorkLogEvent} from '../../lib/activity';
import StatCard from '../../components/dashboard/StatCard';
import {Empty, ErrorMessage, Loader, StatusBadge} from '../../components/common/UI';

function QueueSection({title, eyebrow, rows, status, emptyTitle, emptyText}) {
  return <section className="card dashboard-attention" style={{marginTop: 18}}>
    <div className="section-head"><div><div className="eyebrow">{eyebrow}</div><h3>{title}</h3></div><Link href={`/officer/submissions?status=${status}`}>View queue <ArrowRight size={14}/></Link></div>
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
  const [recent, setRecent] = useState([]);
  const [activity, setActivity] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.officerDashboard(), api.submissions({status: 'SUBMITTED'}), api.submissions({status: 'NEEDS_REVIEW'}), api.submissions(), api.audit().catch(() => [])])
      .then(([dashboard, pendingRows, reviewRows, allRows, events]) => {
        setStats(dashboard); setSubmitted(pendingRows); setNeedsReview(reviewRows); setRecent(allRows.slice(0, 5)); setActivity(events.filter(isWorkLogEvent).slice(0, 5));
      }).catch(loadError => setError(loadError.message));
  }, []);

  if (!stats) return error ? <ErrorMessage>{error}</ErrorMessage> : <Loader label="Preparing today's work queue…"/>;
  return <>
    <div className="page-title officer-page-title"><div><div className="eyebrow">OFFICER WORKSPACE</div><h2>Verification work, prioritized.</h2><p>Start with records that need a decision, then keep the verified repository current.</p></div><Link className="button" href="/officer/submissions?status=SUBMITTED"><Inbox size={16}/> Review next record</Link></div>
    <ErrorMessage>{error}</ErrorMessage>
    <div className="stat-grid officer-stat-grid">
      <StatCard label="Pending review" value={stats.pending} icon={Inbox} href="/officer/submissions?status=SUBMITTED"/>
      <StatCard label="Needs attention" value={stats.needs_review} icon={AlertTriangle} tone="amber" href="/officer/submissions?status=NEEDS_REVIEW"/>
      <StatCard label="Rejected" value={stats.rejected} icon={XCircle} tone="red" href="/officer/submissions?status=REJECTED"/>
      <StatCard label="Verified records" value={stats.verified} icon={CheckCircle} tone="green" href="/officer/records"/>
    </div>
    <div className="quick-actions officer-quick-actions" aria-label="Quick actions">
      <Link className="quick-action" href="/officer/submissions?status=SUBMITTED"><ClipboardCheck size={19}/> Review the next submission</Link>
      <Link className="quick-action" href="/officer/submissions"><ListFilter size={19}/> Open review queue</Link>
      <Link className="quick-action" href="/officer/records"><FileSearch size={19}/> Search verified records</Link>
      <Link className="quick-action" href="/officer/records"><CheckCircle size={19}/> View verified records</Link>
    </div>
    <QueueSection title="Needs your attention" eyebrow="ACTION REQUIRED" rows={needsReview} status="NEEDS_REVIEW" emptyTitle="No records waiting for attention" emptyText="Records needing further review will appear here."/>
    <QueueSection title="Pending review" eyebrow="NEW SUBMISSIONS" rows={submitted} status="SUBMITTED" emptyTitle="No records waiting for review" emptyText="New submissions will appear here automatically."/>
    <section className="card" style={{marginTop: 18}}><div className="section-head"><div><div className="eyebrow">LATEST INTAKE</div><h3>Recent submissions</h3></div><Link href="/officer/submissions">View all <ArrowRight size={14}/></Link></div>
      {!recent.length ? <Empty title="No submissions yet" text="New citizen and officer submissions will appear here."/> : <div className="table-wrap"><table className="data-table"><thead><tr><th>RECORD</th><th>SUBMITTED BY</th><th>LOCATION</th><th>RECEIVED</th><th>STATUS</th></tr></thead><tbody>{recent.map(row => <tr key={row.id}><td><Link href={`/officer/review/${row.document_id}`}>#{row.id} · {row.document?.original_filename || 'Land record'}</Link></td><td>{row.user?.name || '—'}</td><td>{[row.document?.village, row.document?.district].filter(Boolean).join(', ') || '—'}</td><td>{new Date(row.submitted_at).toLocaleString()}</td><td><StatusBadge status={row.status}/></td></tr>)}</tbody></table></div>}
    </section>
    <section className="card" style={{marginTop: 18}}><div className="section-head"><div><div className="eyebrow">RECENT WORK</div><h3>Latest actions</h3></div><Link href="/officer/audit">Work Log <ArrowRight size={14}/></Link></div>
      {!activity.length ? <Empty title="No recent work" text="Document uploads and review actions will appear here."/> : <div className="activity-list">{activity.map(event => <div className="activity-list-item" key={event.id}><span className="activity-list-icon"><Activity size={15}/></span><div><b>{activityLabel(event.action)}</b><p>{activityDescription(event)}</p></div><time>{new Date(event.timestamp).toLocaleString()}</time></div>)}</div>}
    </section>
  </>;
}
