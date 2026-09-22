'use client';

import {useEffect, useState} from 'react';
import {CheckCircle2, Search} from 'lucide-react';
import {api} from '../../../lib/api';
import {CitizenVerifiedDownload} from '../../../components/exports/ExportControls';
import {Empty, ErrorMessage, Loader, Toast} from '../../../components/common/UI';

export default function Records() {
  const [rows, setRows] = useState(null); const [q, setQ] = useState(''); const [error, setError] = useState(''); const [feedback, setFeedback] = useState(null); const [searching, setSearching] = useState(false);
  async function find(nextQuery = q) { if (searching) return; setSearching(true); try { setError(''); setRows(await api.userSubmissions({status:'VERIFIED', search:nextQuery})); } catch { setError('We could not load your verified records. Please try again.'); } finally { setSearching(false); } }
  useEffect(() => { find(''); }, []);
  return <>
    <div className="page-title citizen-page-title"><div><div className="eyebrow">VERIFIED RECORDS</div><h2>Your verified records</h2><p>Download the verified PDF for records that have completed officer review.</p></div></div>
    <div className="search citizen-search"><input value={q} onChange={event => setQ(event.target.value)} onKeyDown={event => event.key === 'Enter' && find()} placeholder="Search document name, village, or record type…"/><button className="button" onClick={() => find()} disabled={searching}>{searching ? 'Searching…' : <><Search size={16}/> Search</>}</button></div>
    <ErrorMessage>{error}</ErrorMessage><Toast message={feedback?.message} tone={feedback?.tone} onDismiss={() => setFeedback(null)}/>
    <section className="card citizen-verified-records" style={{marginTop:16}}>{!rows ? <Loader label="Loading verified records…"/> : !rows.length ? <Empty title="No verified records found" text="Verified records will appear here after officer review is complete."/> : <div className="table-wrap"><table className="data-table citizen-submission-table"><thead><tr><th>VERIFIED RECORD</th><th>DOCUMENT</th><th>LOCATION</th><th>VERIFIED</th><th>DOWNLOAD</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><span className="verified-record-label"><CheckCircle2 size={16}/><b>{row.verified_record?.record_id || `Submission #${row.id}`}</b></span></td><td><b>{row.document?.original_filename || 'Land record'}</b><br/><small>{row.document?.document_type || 'Land record'}</small></td><td>{[row.document?.village, row.document?.district, row.document?.state].filter(Boolean).join(', ') || 'Location unavailable'}</td><td>{row.verified_record?.verified_at ? new Date(row.verified_record.verified_at).toLocaleDateString() : 'Verification complete'}</td><td>{row.verified_record_id ? <CitizenVerifiedDownload recordId={row.verified_record_id} onFeedback={setFeedback}/> : <small>Download will be available shortly.</small>}</td></tr>)}</tbody></table></div>}</section>
  </>;
}
