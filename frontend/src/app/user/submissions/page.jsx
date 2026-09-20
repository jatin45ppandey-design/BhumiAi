'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';
import {Search} from 'lucide-react';
import {api} from '../../../lib/api';
import {getUser} from '../../../lib/auth';
import {Loader, Empty, ErrorMessage, StatusBadge} from '../../../components/common/UI';

const tabs = [['All', ''], ['Pending', 'SUBMITTED'], ['Processing', 'PROCESSING'], ['Needs Review', 'NEEDS_REVIEW'], ['Verified', 'VERIFIED'], ['Rejected', 'REJECTED']];

export default function Submissions() {
  const params = useSearchParams();
  const initialStatus = tabs.some(([, value]) => value === params.get('status')) ? params.get('status') : '';
  const [status, setStatus] = useState(initialStatus);
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState(params.get('search') || '');
  const [error, setError] = useState('');
  const user = getUser();
  async function load(nextStatus = status, nextSearch = q) {
    try { setError(''); setRows(await api.userSubmissions(user.id, {status: nextStatus, search: nextSearch})); }
    catch (loadError) { setError(loadError.message); }
  }
  useEffect(() => { if (user?.id) load(initialStatus, params.get('search') || ''); }, [params]);
  function selectTab(nextStatus) { setStatus(nextStatus); load(nextStatus, q); }

  return <>
    <div className="page-title"><div><div className="eyebrow">MY RECORDS</div><h2>My Submissions</h2><p>Track the current status of your own submitted land records.</p></div><Link className="button" href="/user/upload">Upload document</Link></div>
    <div className="tabs">{tabs.map(([label, value]) => <button key={label} className={`tab ${status === value ? 'active' : ''}`} onClick={() => selectTab(value)}>{label}</button>)}</div>
    <div className="search"><input value={q} onChange={event => setQ(event.target.value)} onKeyDown={event => event.key === 'Enter' && load()} placeholder="Search your document, ID, village, or status…"/><button className="button" onClick={() => load()}><Search size={16}/> Search</button></div>
    <ErrorMessage>{error}</ErrorMessage>
    <section className="card" style={{marginTop: 16}}>{!rows ? <Loader/> : !rows.length ? <Empty title="No matching submissions" text="Try another status or search term."/> : <div className="table-wrap"><table className="data-table"><thead><tr><th>RECORD ID</th><th>DOCUMENT</th><th>LOCATION</th><th>SUBMISSION DATE</th><th>STATUS</th><th>DETAIL</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>#{row.id}</td><td>{row.document?.original_filename || 'Land record'}<br/><small>{row.document?.document_type}</small></td><td>{[row.document?.village, row.document?.district].filter(Boolean).join(', ') || '—'}</td><td>{new Date(row.submitted_at).toLocaleString()}</td><td><StatusBadge status={row.status}/></td><td>{row.status === 'REJECTED' ? <div className="rejection-detail"><b>{row.rejection?.reason_category || 'Reason unavailable'}</b>{row.rejection?.officer_note && <><br/>{row.rejection.officer_note}</>}</div> : row.status === 'VERIFIED' ? 'Verified record available' : '—'}</td></tr>)}</tbody></table></div>}</section>
  </>;
}
