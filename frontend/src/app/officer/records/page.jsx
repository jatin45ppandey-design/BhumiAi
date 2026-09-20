'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {Search} from 'lucide-react';
import {api} from '../../../lib/api';
import {Empty, ErrorMessage, Loader} from '../../../components/common/UI';

function DigitizationSummary({record}) {
  const summary = record.digitization_summary || {};
  const parts = [];
  if (summary.fields_detected) parts.push(`${summary.fields_detected} fields`);
  if (summary.tables_detected) parts.push(`${summary.tables_detected} tables`);
  if (summary.rows_digitized) parts.push(`${summary.rows_digitized} rows`);
  if (summary.cells_digitized) parts.push(`${summary.cells_digitized} cells`);
  if (parts.length) return parts.join(' · ');

  const legacy = [record.owner_name, record.khasra_number, record.khata_number].filter(Boolean);
  return legacy.length ? `Legacy summary: ${legacy.join(' · ')}` : 'No document-native fields stored';
}

export default function Records() {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState('');
  const [err, setErr] = useState('');

  async function load() {
    try {
      setErr('');
      setRows(await api.records(q));
    } catch (error) {
      setErr(error.message);
    }
  }

  useEffect(() => { load(); }, []);

  return <>
    <div className="page-title">
      <div>
        <div className="eyebrow">PERMANENT REPOSITORY</div>
        <h2>Verified Records</h2>
        <p>Officer-approved records retain the actual fields, table structure, and source evidence from each document.</p>
      </div>
    </div>
    <div className="search">
      <input
        value={q}
        onChange={event => setQ(event.target.value)}
        onKeyDown={event => event.key === 'Enter' && load()}
        placeholder="Record ID, metadata, detected label, field value, or table cell…"
      />
      <button className="button" onClick={load}><Search size={16}/> Search</button>
    </div>
    <ErrorMessage>{err}</ErrorMessage>
    <section className="card" style={{marginTop: 16}}>
      {!rows ? <Loader/> : !rows.length ? <Empty title="No verified records found" text="Search uses source metadata plus dynamic fields, headers, and cells."/> :
        <div className="table-wrap"><table className="data-table">
          <thead><tr><th>RECORD ID</th><th>SOURCE DOCUMENT</th><th>DIGITIZED STRUCTURE</th><th>LOCATION</th><th>VERIFIED</th><th></th></tr></thead>
          <tbody>{rows.map(record => <tr key={record.id}>
            <td><b>{record.record_id}</b></td>
            <td>{record.document_name || '—'}<br/><small>{record.document_type || 'Source type unavailable'}</small></td>
            <td>{<DigitizationSummary record={record}/>}</td>
            <td>{[record.village, record.district, record.state].filter(Boolean).join(', ') || '—'}</td>
            <td>{record.verified_at ? new Date(record.verified_at).toLocaleDateString() : '—'}</td>
            <td><Link className="button secondary" href={`/officer/records/${record.id}`}>View record</Link></td>
          </tr>)}</tbody>
        </table></div>}
    </section>
  </>;
}
