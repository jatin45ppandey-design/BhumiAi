'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, CheckCircle, Clock, Files, Inbox, ScanText } from 'lucide-react';
import { api } from '../../lib/api';
import StatCard from '../../components/dashboard/StatCard';
import { Empty, ErrorMessage, Loader, StatusBadge } from '../../components/common/UI';

export default function OfficerDashboard() {
  const [stats, setStats] = useState(null);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.officerDashboard(), api.submissions()]).then(([dashboard, submissions]) => {
      setStats(dashboard);
      setRows(submissions.slice(0, 5));
    }).catch(loadError => setError(loadError.message));
  }, []);

  if (!stats) return <Loader label="Loading verification overview..." />;

  return <>
    <div className="page-title"><div><div className="eyebrow">OVERVIEW</div><h2>Verification overview</h2><p>Monitor digitization, review, and verification activity across the current record queue.</p></div><Link className="button" href="/officer/upload">Digitize Record</Link></div>
    <ErrorMessage>{error}</ErrorMessage>
    <div className="stat-grid">
      <StatCard label="Total records" value={stats.total_received} icon={Inbox} />
      <StatCard label="Awaiting review" value={stats.pending} icon={Clock} tone="amber" />
      <StatCard label="Processing" value={stats.processing} icon={Files} />
      <StatCard label="Digitized" value={stats.digitized} icon={ScanText} />
      <StatCard label="Verified records" value={stats.verified} icon={CheckCircle} tone="green" />
      <StatCard label="Needs review" value={stats.needs_review} icon={AlertTriangle} tone="amber" />
    </div>
    <section className="card" style={{ marginTop: 18 }}><div className="section-head"><div><div className="eyebrow">WORKFLOW</div><h3>Record activity</h3><p>Live counts from the current workspace.</p></div></div><div className="pipeline"><div><b>RECEIVED</b><strong>{stats.total_received}</strong></div><div><b>PROCESSING</b><strong>{stats.processing}</strong></div><div><b>REVIEW</b><strong>{stats.needs_review}</strong></div><div><b>VERIFIED</b><strong>{stats.verified}</strong></div></div></section>
    <section className="card" style={{ marginTop: 18 }}><div className="section-head"><div><div className="eyebrow">REVIEW QUEUE</div><h3>Recent records</h3><p>Open a source record to review its structured digital version.</p></div><Link href="/officer/submissions">View queue</Link></div>
      {rows.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>RECORD</th><th>SOURCE DOCUMENT</th><th>SUBMITTER</th><th>STATUS</th><th /></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>#{row.id}</td><td>{row.document?.original_filename}</td><td>{row.user?.name || '—'}</td><td><StatusBadge status={row.status} /></td><td><Link className="button secondary" href={`/officer/review/${row.document_id}`}>Open review</Link></td></tr>)}</tbody></table></div> : <Empty title="No records awaiting review" text="Newly submitted land records will appear here." />}
    </section>
  </>;
}
