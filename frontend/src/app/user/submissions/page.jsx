'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';
import {Search, X} from 'lucide-react';
import {api} from '../../../lib/api';
import {CitizenVerifiedDownload} from '../../../components/exports/ExportControls';
import {Button, Loader, Empty, ErrorMessage, StatusBadge, Toast} from '../../../components/common/UI';

const tabs = [['All', ''], ['Pending', 'SUBMITTED'], ['Processing', 'PROCESSING'], ['Needs Review', 'NEEDS_REVIEW'], ['Verified', 'VERIFIED'], ['Rejected', 'REJECTED']];

export default function Submissions() {
  const params = useSearchParams();
  const initialStatus = tabs.some(([, value]) => value === params.get('status')) ? params.get('status') : '';
  const [status, setStatus] = useState(initialStatus);
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState(params.get('search') || '');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [searching, setSearching] = useState(false);

  async function load(nextStatus = status, nextSearch = q) {
    if (searching) return;
    setSearching(true);
    try {
      setError('');
      setRows(await api.userSubmissions({status: nextStatus, search: nextSearch}));
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setSearching(false);
    }
  }

  useEffect(() => {
    setStatus(initialStatus);
    setQ(params.get('search') || '');
    load(initialStatus, params.get('search') || '');
  }, [params, initialStatus]);

  function selectTab(nextStatus) {
    setStatus(nextStatus);
    load(nextStatus, q);
  }

  return <>
    <div className="page-title">
      <div><div className="eyebrow">MY RECORDS</div><h2>My Submissions</h2><p>Track the current status of your own submitted land records.</p></div>
      <Link className="button" href="/user/upload">Upload document</Link>
    </div>
    <div className="tabs">{tabs.map(([label, value]) => <button key={label} disabled={searching} className={`tab ${status === value ? 'active' : ''}`} onClick={() => selectTab(value)}>{label}</button>)}</div>
    <div className="search">
      <input aria-label="Search my submissions" value={q} onChange={event => setQ(event.target.value)} onKeyDown={event => event.key === 'Enter' && load()} placeholder="Search document, record ID, village, or status..."/>
      {q && <button type="button" className="search-clear" onClick={() => { setQ(''); load(status, ''); }}><X size={15}/> Clear</button>}
      <Button onClick={() => load()} loading={searching} loadingText="Searching..."><Search size={16}/> Search</Button>
    </div>
    <ErrorMessage>{error}</ErrorMessage>
    <Toast message={feedback?.message} tone={feedback?.tone} onDismiss={() => setFeedback(null)}/>
    <section className="card" style={{marginTop: 16}}>
      {!rows ? <Loader/> : !rows.length ? <Empty title="No matching submissions" text="Try another status or search term."/> :
        <div className="table-wrap"><table className="data-table">
          <thead><tr><th>RECORD ID</th><th>DOCUMENT</th><th>LOCATION</th><th>SUBMISSION DATE</th><th>STATUS</th><th>DETAIL</th></tr></thead>
          <tbody>{rows.map(row => <tr key={row.id}>
            <td>#{row.id}</td>
            <td>{row.document?.original_filename || 'Land record'}<br/><small>{row.document?.document_type}</small></td>
            <td>{[row.document?.village, row.document?.district].filter(Boolean).join(', ') || '—'}</td>
            <td>{new Date(row.submitted_at).toLocaleString()}</td>
            <td><StatusBadge status={row.status}/></td>
            <td>{row.status === 'REJECTED' ? <div className="rejection-detail"><b>{row.rejection?.reason_category || 'Reason unavailable'}</b>{row.rejection?.officer_note && <><br/>{row.rejection.officer_note}</>}</div> : row.status === 'VERIFIED' ? <div className="verified-download"><span>Verified record available</span>{row.verified_record_id ? <CitizenVerifiedDownload recordId={row.verified_record_id} onFeedback={setFeedback}/> : null}</div> : '—'}</td>
          </tr>)}</tbody>
        </table></div>}
    </section>
  </>;
}
