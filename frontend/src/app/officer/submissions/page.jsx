'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';
import {Search, X} from 'lucide-react';
import {api} from '../../../lib/api';
import {Button, Loader, Empty, ErrorMessage, StatusBadge} from '../../../components/common/UI';

const tabs = [['All', ''], ['New', 'SUBMITTED'], ['Processing', 'PROCESSING'], ['Needs Review', 'NEEDS_REVIEW'], ['Verified', 'VERIFIED'], ['Rejected', 'REJECTED']];
const actionFor = row => ({
  SUBMITTED: ['Open review', `/officer/review/${row.document_id}`], PROCESSING: ['Continue review', `/officer/review/${row.document_id}`], NEEDS_REVIEW: ['Review again', `/officer/review/${row.document_id}`],
  VERIFIED: ['View verified record', row.verified_record_id ? `/officer/records/${row.verified_record_id}` : `/officer/review/${row.document_id}`], REJECTED: ['View details', `/officer/review/${row.document_id}`],
}[row.status] || ['View details', `/officer/review/${row.document_id}`]);

export default function Submissions() {
  const params = useSearchParams();
  const initialStatus = tabs.some(([, value]) => value === params.get('status')) ? params.get('status') : '';
  const [status, setStatus] = useState(initialStatus); const [rows, setRows] = useState(null); const [q, setQ] = useState(params.get('search') || ''); const [err, setErr] = useState(''); const [searching, setSearching] = useState(false);
  async function load(nextStatus = status, nextSearch = q) { if (searching) return; setSearching(true); try { setErr(''); setRows(await api.submissions({status: nextStatus, search: nextSearch})); } catch (error) { setErr(error.message); } finally { setSearching(false); } }
  useEffect(() => { setStatus(initialStatus); setQ(params.get('search') || ''); load(initialStatus, params.get('search') || ''); }, [params, initialStatus]);
  function selectTab(nextStatus) { setStatus(nextStatus); load(nextStatus, q); }

  return <>
    <div className="page-title queue-page-title"><div><div className="eyebrow">REVIEW QUEUE</div><h2>Incoming records</h2><p>Prioritize attention items, then open a record when you are ready to verify it.</p></div></div>
    <div className="queue-controls"><div className="tabs">{tabs.map(([label, value]) => <button key={label} disabled={searching} className={`tab ${status === value ? 'active' : ''}`} onClick={() => selectTab(value)}>{label}</button>)}</div><div className="search queue-search"><input aria-label="Search submissions" value={q} onChange={event => setQ(event.target.value)} onKeyDown={event => event.key === 'Enter' && load()} placeholder="Search record ID, document, citizen, or location…"/>{q && <button type="button" className="search-clear" onClick={() => { setQ(''); load(status, ''); }}><X size={15}/> Clear</button>}<Button onClick={() => load()} loading={searching} loadingText="Searching…"><Search size={16}/> Search</Button></div></div>
    <ErrorMessage>{err}</ErrorMessage>
    <section className="card queue-card" style={{marginTop: 16}}>{!rows ? <Loader label="Loading review queue…"/> : !rows.length ? <Empty title="No matching submissions" text="Try another status or search term."/> : <div className="table-wrap"><table className="data-table queue-table"><thead><tr><th>RECORD</th><th>CITIZEN</th><th>DOCUMENT</th><th>LOCATION</th><th>RECEIVED</th><th>STATUS</th><th/></tr></thead><tbody>{rows.map(row => { const [label, href] = actionFor(row); const attention = row.status === 'NEEDS_REVIEW' || row.status === 'PROCESSING'; return <tr className={attention ? 'queue-row attention' : 'queue-row'} key={row.id}><td><b>#{row.id}</b><br/><small>{attention ? 'Attention required' : 'Ready for review'}</small></td><td>{row.user?.name || '—'}<br/><small>{row.user?.email}</small></td><td><b>{row.document?.original_filename || '—'}</b><br/><small>{row.document?.document_type || 'Land record'}</small></td><td>{[row.document?.village, row.document?.district, row.document?.state].filter(Boolean).join(', ') || '—'}{row.rejection?.reason_category && <div className="rejection-detail">Reason: {row.rejection.reason_category}</div>}</td><td>{new Date(row.submitted_at).toLocaleString()}</td><td><StatusBadge status={row.status}/></td><td><Link className="button secondary" href={href}>{label}</Link></td></tr>; })}</tbody></table></div>}</section>
  </>;
}
