'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {Search} from 'lucide-react';
import {api} from '../../../lib/api';
import {Empty, ErrorMessage, Loader} from '../../../components/common/UI';

function DigitizationSummary({record}) {
  const summary = record.digitization_summary || {};
  const parts = [];
  if (summary.fields_detected) parts.push(`${summary.fields_detected} field${summary.fields_detected === 1 ? '' : 's'}`);
  if (summary.tables_detected) parts.push(`${summary.tables_detected} table${summary.tables_detected === 1 ? '' : 's'}`);
  if (summary.cells_digitized) parts.push(`${summary.cells_digitized} cell${summary.cells_digitized === 1 ? '' : 's'}`);

  if (parts.length) return <span>{parts.join(' · ')}</span>;
  const legacy = [record.owner_name, record.khasra_number].filter(Boolean).join(' · ');
  return <span>{legacy || 'No document-native fields stored'}</span>;
}

export default function Records() {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState('');
  const [err, setErr] = useState('');

  async function find() {
    try {
      setErr('');
      setRows(await api.records(q));
    } catch (error) {
      setErr(error.message);
    }
  }

  useEffect(() => { find(); }, []);

  return <>
    <div className="page-title">
      <div>
        <div className="eyebrow">REPOSITORY</div>
        <h2>Verified Records</h2>
        <p>Search permanent records by source metadata or any digitized document label and value.</p>
      </div>
    </div>
    <div className="search">
      <input
        value={q}
        onChange={event => setQ(event.target.value)}
        onKeyDown={event => event.key === 'Enter' && find()}
        placeholder="Record ID, document metadata, detected label, or value…"
      />
      <button className="button" onClick={find}><Search size={16}/> Search</button>
    </div>
    <ErrorMessage>{err}</ErrorMessage>
    <section className="card" style={{marginTop: 16}}>
      {!rows ? <Loader/> : !rows.length ? <Empty title="No verified records found" text="Try a document label, a digitized value, or source metadata."/> :
        <div className="table-wrap"><table className="data-table">
          <thead><tr><th>RECORD ID</th><th>DOCUMENT</th><th>DIGITIZED CONTENT</th><th>LOCATION</th><th>VERIFIED</th></tr></thead>
          <tbody>{rows.map(record => <tr key={record.id}>
            <td><Link href={`/officer/records/${record.id}`}>{record.record_id}</Link></td>
            <td><b>{record.document_name || '—'}</b><br/><small>{record.document_type || 'Source type unavailable'}</small></td>
            <td><DigitizationSummary record={record}/></td>
            <td>{[record.village, record.district, record.state].filter(Boolean).join(', ') || '—'}</td>
            <td>{record.verified_at ? new Date(record.verified_at).toLocaleDateString() : '—'}</td>
          </tr>)}</tbody>
        </table></div>}
    </section>
  </>;
}
