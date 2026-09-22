'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';
import {CheckCircle2, Clock3, Search, X} from 'lucide-react';
import {api} from '../../../lib/api';
import {CitizenVerifiedDownload} from '../../../components/exports/ExportControls';
import {Button, Loader, Empty, ErrorMessage, StatusBadge, Toast} from '../../../components/common/UI';

const tabs = [['All', ''], ['Submitted', 'SUBMITTED'], ['Processing', 'PROCESSING'], ['Under review', 'NEEDS_REVIEW'], ['Verified', 'VERIFIED'], ['Rejected', 'REJECTED']];
const statusCopy = status => ({
  SUBMITTED: ['Submitted', 'Your submission is waiting to be processed.'], PROCESSING: ['Processing', 'Your document is being processed.'], NEEDS_REVIEW: ['Under officer review', 'A verification officer is reviewing this record.'], VERIFIED: ['Verified record', 'Verification complete. Your record is ready to download.'], REJECTED: ['Not verified', 'This submission was not verified. See the reason below.'],
}[status] || ['Status update', 'Your record status will be shown here.']);

function SubmissionAction({row, onFeedback}) {
  if (row.status === 'VERIFIED') return <div className="verified-download"><span><CheckCircle2 size={13}/> Verified record available</span>{row.verified_record_id ? <CitizenVerifiedDownload recordId={row.verified_record_id} onFeedback={onFeedback}/> : null}</div>;
  if (row.status === 'REJECTED') return <div className="rejection-detail"><b>{row.rejection?.reason_category || 'Reason unavailable'}</b>{row.rejection?.officer_note && <><br/>{row.rejection.officer_note}</>}</div>;
  return <span className="submission-awaiting"><Clock3 size={13}/> No action needed right now</span>;
}

export default function Submissions() {
  const params = useSearchParams(); const initialStatus = tabs.some(([, value]) => value === params.get('status')) ? params.get('status') : '';
  const [status, setStatus] = useState(initialStatus); const [rows, setRows] = useState(null); const [q, setQ] = useState(params.get('search') || ''); const [error, setError] = useState(''); const [feedback, setFeedback] = useState(null); const [searching, setSearching] = useState(false);
  async function load(nextStatus = status, nextSearch = q) { if (searching) return; setSearching(true); try { setError(''); setRows(await api.userSubmissions({status: nextStatus, search: nextSearch})); } catch { setError('We could not load your submissions. Please try again.'); } finally { setSearching(false); } }
  useEffect(() => { setStatus(initialStatus); setQ(params.get('search') || ''); load(initialStatus, params.get('search') || ''); }, [params, initialStatus]);
  function selectTab(nextStatus) { setStatus(nextStatus); load(nextStatus, q); }
  return <>
    <div className="page-title citizen-page-title"><div><div className="eyebrow">MY SUBMISSIONS</div><h2>Track your submitted records</h2><p>Each record shows its current review status and next available action.</p></div><Link className="button" href="/user/upload">Upload record</Link></div>
    <div className="citizen-submission-controls"><div className="tabs">{tabs.map(([label, value]) => <button key={label} disabled={searching} className={`tab ${status === value ? 'active' : ''}`} onClick={() => selectTab(value)}>{label}</button>)}</div><div className="search citizen-search"><input aria-label="Search my submissions" value={q} onChange={event => setQ(event.target.value)} onKeyDown={event => event.key === 'Enter' && load()} placeholder="Search document, village, or status…"/>{q && <button type="button" className="search-clear" onClick={() => { setQ(''); load(status, ''); }}><X size={15}/> Clear</button>}<Button onClick={() => load()} loading={searching} loadingText="Searching…"><Search size={16}/> Search</Button></div></div>
    <ErrorMessage>{error}</ErrorMessage><Toast message={feedback?.message} tone={feedback?.tone} onDismiss={() => setFeedback(null)}/>
    <section className="card citizen-submission-list" style={{marginTop:16}}>{!rows ? <Loader label="Loading your submissions…"/> : !rows.length ? <Empty title="No matching submissions" text="Try another status or search term."/> : <div className="table-wrap"><table className="data-table citizen-submission-table"><thead><tr><th>RECORD</th><th>DOCUMENT</th><th>SUBMITTED</th><th>STATUS</th><th>WHAT’S HAPPENING</th><th>ACTION</th></tr></thead><tbody>{rows.map(row => { const [label, description] = statusCopy(row.status); return <tr key={row.id}><td><b>#{row.id}</b><br/><small>{[row.document?.village, row.document?.district].filter(Boolean).join(', ') || 'Location unavailable'}</small></td><td><b>{row.document?.original_filename || 'Land record'}</b><br/><small>{row.document?.document_type || 'Land record'}</small></td><td>{new Date(row.submitted_at).toLocaleDateString()}</td><td><StatusBadge status={row.status}/><br/><small>{label}</small></td><td className="submission-status-copy">{description}</td><td><SubmissionAction row={row} onFeedback={setFeedback}/></td></tr>; })}</tbody></table></div>}</section>
  </>;
}
