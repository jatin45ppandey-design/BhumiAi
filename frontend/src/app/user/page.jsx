'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {AlertTriangle, CheckCircle, Clock3, FilePlus2, Files, RefreshCw, XCircle} from 'lucide-react';
import {api} from '../../lib/api';
import StatCard from '../../components/dashboard/StatCard';
import {Loader, Empty, ErrorMessage, StatusBadge} from '../../components/common/UI';

const statusMessage = status => ({
  SUBMITTED: 'Your submission is waiting to be processed.', PROCESSING: 'Your document is being processed.', NEEDS_REVIEW: 'A verification officer is reviewing this record.', VERIFIED: 'Verification complete.', REJECTED: 'This submission was not verified. Review the reason provided.',
}[status] || 'Your record status will be updated here.');

export default function UserDashboard() {
  const [stats, setStats] = useState(null); const [rows, setRows] = useState([]); const [notifications, setNotifications] = useState([]); const [error, setError] = useState('');
  useEffect(() => { Promise.all([api.userDashboard(), api.userSubmissions(), api.notifications()]).then(([dashboard, submissions, notices]) => { setStats(dashboard); setRows(submissions.slice(0, 5)); setNotifications(notices.slice(0, 3)); }).catch(() => setError('We could not load your record overview. Please try again.')); }, []);
  if (!stats) return error ? <ErrorMessage>{error}</ErrorMessage> : <Loader label="Loading your records…"/>;
  const inProgress = (stats.pending_review || 0) + (stats.processing || 0);
  return <>
    <div className="page-title citizen-page-title"><div><div className="eyebrow">MY RECORDS</div><h2>What is happening with my records?</h2><p>See each submission’s current status, from upload through officer verification.</p></div><Link className="button" href="/user/upload"><FilePlus2 size={16}/> Upload record</Link></div>
    <ErrorMessage>{error}</ErrorMessage>
    <div className="stat-grid citizen-stat-grid"><StatCard label="Total submitted" value={stats.total_submitted} icon={Files} href="/user/submissions"/><StatCard label="Processing or review" value={inProgress} icon={RefreshCw} tone="amber" href="/user/submissions?status=PROCESSING"/><StatCard label="Needs attention" value={stats.needs_review} icon={AlertTriangle} tone="amber" href="/user/submissions?status=NEEDS_REVIEW"/><StatCard label="Verified" value={stats.verified} icon={CheckCircle} tone="green" href="/user/submissions?status=VERIFIED"/><StatCard label="Rejected" value={stats.rejected} icon={XCircle} tone="red" href="/user/submissions?status=REJECTED"/></div>
    {notifications.length > 0 && <section className="card citizen-notifications" style={{marginTop:20}}><div className="section-head"><div><div className="eyebrow">NOTIFICATIONS</div><h3>Record notices</h3><p>Updates related to your submitted records.</p></div></div><div className="notification-list">{notifications.map(notice => <div className="notification-item" key={notice.id}><Clock3 size={16}/><div><b>{notice.title}</b><p>{notice.message}</p></div><time>{new Date(notice.created_at).toLocaleDateString()}</time></div>)}</div></section>}
    <section className="card citizen-recent-submissions" style={{marginTop:20}}><div className="section-head"><div><div className="eyebrow">RECENT SUBMISSIONS</div><h3>Your latest records</h3><p>Open all submissions to search and download verified records.</p></div><Link href="/user/submissions">View all</Link></div>{rows.length ? <div className="table-wrap"><table className="data-table citizen-table"><thead><tr><th>SUBMISSION</th><th>DOCUMENT</th><th>STATUS</th><th>SUBMITTED</th><th>UPDATE</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><b>#{row.id}</b></td><td><b>{row.document?.original_filename || 'Land record'}</b><br/><small>{row.document?.document_type || 'Land record'}</small></td><td><StatusBadge status={row.status}/></td><td>{new Date(row.submitted_at).toLocaleDateString()}</td><td>{row.status === 'REJECTED' ? <span className="rejection-detail">{row.rejection?.reason_category || 'Reason unavailable'}</span> : <small>{statusMessage(row.status)}</small>}</td></tr>)}</tbody></table></div> : <Empty title="No submissions yet" text="Upload a scanned or photographed land record to start verification."/>}</section>
  </>;
}
