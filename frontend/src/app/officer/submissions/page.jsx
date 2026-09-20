'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';
import {Search} from 'lucide-react';
import {api} from '../../../lib/api';
import {Loader, Empty, ErrorMessage, StatusBadge} from '../../../components/common/UI';

const tabs = [['All', ''], ['New', 'SUBMITTED'], ['Processing', 'PROCESSING'], ['Needs Review', 'NEEDS_REVIEW'], ['Verified', 'VERIFIED'], ['Rejected', 'REJECTED']];
const actionFor = row => ({
  SUBMITTED: ['Open Review', `/officer/review/${row.document_id}`],
  PROCESSING: ['Continue Review', `/officer/review/${row.document_id}`],
  NEEDS_REVIEW: ['Review Again', `/officer/review/${row.document_id}`],
  VERIFIED: ['View Verified Record', row.verified_record_id ? `/officer/records/${row.verified_record_id}` : `/officer/review/${row.document_id}`],
  REJECTED: ['View Details', `/officer/review/${row.document_id}`],
}[row.status] || ['View Details', `/officer/review/${row.document_id}`]);

export default function Submissions() {
  const params = useSearchParams();
  const initialStatus = tabs.some(([, value]) => value === params.get('status')) ? params.get('status') : '';
  const [status, setStatus] = useState(initialStatus);
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState(params.get('search') || '');
  const [err, setErr] = useState('');

  async function load(nextStatus = status, nextSearch = q) {
    try { setErr(''); setRows(await api.submissions({status: nextStatus, search: nextSearch})); }
    catch (error) { setErr(error.message); }
  }
  useEffect(() => { load(initialStatus, params.get('search') || ''); }, [params]);
  function selectTab(nextStatus) { setStatus(nextStatus); load(nextStatus, q); }

  return <>
    <div className="page-title"><div><div className="eyebrow">RECORD WORKSPACE</div><h2>Incoming records</h2><p>Filter the operational queue without starting document processing.</p></div></div>
    <div className="tabs">{tabs.map(([label, value]) => <button key={label} className={`tab ${status === value ? 'active' : ''}`} onClick={() => selectTab(value)}>{label}</button>)}</div>
    <div className="search"><input value={q} onChange={event => setQ(event.target.value)} onKeyDown={event => event.key === 'Enter' && load()} placeholder="Search ID, document, citizen, email, or location…"/><button className="button" onClick={() => load()}><Search size={16}/> Search</button></div>
    <ErrorMessage>{err}</ErrorMessage>
    <section className="card" style={{marginTop: 16}}>{!rows ? <Loader/> : !rows.length ? <Empty title="No matching submissions" text="Try another status or search term."/> : <div className="table-wrap"><table className="data-table"><thead><tr><th>RECORD ID</th><th>CITIZEN</th><th>DOCUMENT</th><th>LOCATION</th><th>SUBMITTED AT</th><th>STATUS</th><th/></tr></thead><tbody>{rows.map(row => { const [label, href] = actionFor(row); return <tr key={row.id}><td>#{row.id}</td><td>{row.user?.name || '—'}<br/><small>{row.user?.email}</small></td><td>{row.document?.original_filename || '—'}<br/><small>{row.document?.document_type}</small></td><td>{[row.document?.village, row.document?.district, row.document?.state].filter(Boolean).join(', ') || '—'}{row.rejection?.reason_category && <div className="rejection-detail">Reason: {row.rejection.reason_category}</div>}</td><td>{new Date(row.submitted_at).toLocaleString()}</td><td><StatusBadge status={row.status}/></td><td><Link className="button secondary" href={href}>{label}</Link></td></tr>; })}</tbody></table></div>}</section>
  </>;
}
