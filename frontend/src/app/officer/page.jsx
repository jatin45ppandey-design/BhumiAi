'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {AlertTriangle, CheckCircle, Clock, Files, Inbox, XCircle} from 'lucide-react';
import {api} from '../../lib/api';
import StatCard from '../../components/dashboard/StatCard';
import {Empty, ErrorMessage, Loader, StatusBadge} from '../../components/common/UI';

function QueueSection({title, eyebrow, rows, status, action = 'Open Review'}) {
  const href = `/officer/submissions?status=${status}`;
  return <section className="card" style={{marginTop: 18}}><div className="section-head"><div><div className="eyebrow">{eyebrow}</div><h3>{title}</h3></div><Link href={href}>View all</Link></div>
    {!rows.length ? <Empty title={`No ${title.toLowerCase()}`} text="Records will appear here as workflow status changes."/> : <div className="table-wrap"><table className="data-table"><thead><tr><th>DOCUMENT</th><th>CITIZEN</th><th>LOCATION</th><th>TIME</th><th>STATUS</th><th/></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.document?.original_filename || '—'}</td><td>{row.user?.name || '—'}</td><td>{[row.document?.village, row.document?.district].filter(Boolean).join(', ') || '—'}{row.rejection?.reason_category && <div className="rejection-detail">{row.rejection.reason_category}</div>}</td><td>{new Date(row.rejection?.rejected_at || row.submitted_at).toLocaleString()}</td><td><StatusBadge status={row.status}/></td><td><Link className="button secondary" href={`/officer/review/${row.document_id}`}>{action}</Link></td></tr>)}</tbody></table></div>}
  </section>;
}

function VerifiedSection({rows}) {
  return <section className="card" style={{marginTop: 18}}><div className="section-head"><div><div className="eyebrow">PERMANENT REPOSITORY</div><h3>Recently Verified</h3></div><Link href="/officer/records">View all</Link></div>
    {!rows.length ? <Empty title="No recently verified records" text="Approved records are retained in the permanent repository."/> : <div className="table-wrap"><table className="data-table"><thead><tr><th>RECORD ID</th><th>SOURCE DOCUMENT</th><th>LOCATION</th><th>VERIFIED</th><th/></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.record_id}</td><td>{row.document_name || '—'}</td><td>{[row.village, row.district, row.state].filter(Boolean).join(', ') || '—'}</td><td>{row.verified_at ? new Date(row.verified_at).toLocaleString() : '—'}</td><td><Link className="button secondary" href={`/officer/records/${row.id}`}>View Record</Link></td></tr>)}</tbody></table></div>}
  </section>;
}

export default function OfficerDashboard() {
  const [stats, setStats] = useState(null);
  const [queues, setQueues] = useState({SUBMITTED: [], NEEDS_REVIEW: [], REJECTED: [], VERIFIED: []});
  const [verified, setVerified] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    Promise.all([api.officerDashboard(), ...['SUBMITTED', 'NEEDS_REVIEW', 'REJECTED', 'VERIFIED'].map(status => api.submissions({status})), api.records()])
      .then(([dashboard, submitted, review, rejected, verifiedSubmissions, records]) => {
        setStats(dashboard); setQueues({SUBMITTED: submitted.slice(0, 5), NEEDS_REVIEW: review.slice(0, 5), REJECTED: rejected.slice(0, 5), VERIFIED: verifiedSubmissions.slice(0, 5)}); setVerified(records.slice(0, 5));
      }).catch(loadError => setError(loadError.message));
  }, []);
  if (!stats) return <Loader label="Loading verification overview..."/>;
  return <>
    <div className="page-title"><div><div className="eyebrow">OVERVIEW</div><h2>Verification overview</h2><p>Direct access to the live operational queue and permanent record repository.</p></div><Link className="button" href="/officer/upload">Digitize Record</Link></div>
    <ErrorMessage>{error}</ErrorMessage>
    <div className="stat-grid"><StatCard label="New Submissions" value={stats.pending} icon={Inbox} href="/officer/submissions?status=SUBMITTED"/><StatCard label="Processing" value={stats.processing} icon={Files} href="/officer/submissions?status=PROCESSING"/><StatCard label="Needs Review" value={stats.needs_review} icon={AlertTriangle} tone="amber" href="/officer/submissions?status=NEEDS_REVIEW"/><StatCard label="Verified" value={stats.verified} icon={CheckCircle} tone="green" href="/officer/records"/><StatCard label="Rejected" value={stats.rejected} icon={XCircle} tone="red" href="/officer/submissions?status=REJECTED"/><StatCard label="All Records" value={stats.total_received} icon={Clock} href="/officer/submissions"/></div>
    <QueueSection title="New Submissions" eyebrow="WORKFLOW QUEUE" rows={queues.SUBMITTED} status="SUBMITTED"/>
    <QueueSection title="Needs Review" eyebrow="OFFICER ACTION" rows={queues.NEEDS_REVIEW} status="NEEDS_REVIEW" action="Review Again"/>
    <VerifiedSection rows={verified}/>
    <QueueSection title="Recently Rejected" eyebrow="READ-ONLY DETAILS" rows={queues.REJECTED} status="REJECTED" action="View Details"/>
  </>;
}
