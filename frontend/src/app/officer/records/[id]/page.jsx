'use client';

import {useEffect, useMemo, useState} from 'react';
import {useParams} from 'next/navigation';
import {API_URL, api} from '../../../../lib/api';
import {bilingualKhatauniLabel} from '../../../../lib/khatauniLabels';
import {ErrorMessage, Loader, StatusBadge} from '../../../../components/common/UI';

const sourceUrl = path => path ? `${API_URL}/uploads/${path.split('\\').pop().split('/').pop()}` : '';
const isPresent = value => value !== null && value !== undefined && value !== '';
const display = value => isPresent(value) ? String(value) : '—';
const label = value => isPresent(value) ? bilingualKhatauniLabel(String(value).replaceAll('_', ' ')) : 'Unlabelled item';
const confidence = value => value === null || value === undefined || value === '' || Number.isNaN(Number(value))
  ? 'Confidence unavailable'
  : `${Math.round(Number(value))}%`;

function DynamicFields({fields}) {
  if (!fields.length) return <p className="muted" style={{padding: '0 18px 18px'}}>No Khatauni header fields were stored for this record.</p>;
  return <div className="table-wrap"><table className="data-table">
    <thead><tr><th>DOCUMENT LABEL</th><th>FINAL VALUE</th><th>OCR / AI VALUE</th><th>CONFIDENCE</th><th>VERIFICATION</th></tr></thead>
    <tbody>{fields.map((field, index) => <tr key={field.field_id || field.id || index}>
      <td><b>{label(field.original_label || field.normalized_label)}</b>{field.normalized_label && field.original_label ? <><br/><small>Normalized: {field.normalized_label}</small></> : null}</td>
      <td>{display(field.display_value || field.final_value || field.officer_value || field.ai_value || field.raw_ocr_value)}</td>
      <td>{display(field.raw_ocr_value || field.ai_value)}</td>
      <td>{confidence(field.ai_confidence)}{field.confidence_source ? <><br/><small>{field.confidence_source}</small></> : null}</td>
      <td>{field.edited ? 'Officer corrected' : 'OCR-derived'}</td>
    </tr>)}</tbody>
  </table></div>;
}

function DigitizedTable({table, number}) {
  const headers = table.headers || [];
  if (!headers.length) return <section className="card" style={{marginTop: 14}}>
    <div className="section-head"><div><h3>{bilingualKhatauniLabel(table.original_label || table.normalized_label) || `Detected table ${number}`}</h3><p>No readable headers or cells were stored for this table.</p></div></div>
  </section>;

  return <section className="card" style={{marginTop: 14}}>
    <div className="section-head"><div>
      <h3>{bilingualKhatauniLabel(table.original_label || table.normalized_label) || `Detected table ${number}`}</h3>
      <p>{table.rows?.length || 0} stored rows · {headers.length} columns · {confidence(table.ai_confidence)}</p>
    </div></div>
    {!table.rows?.length ? <p className="muted" style={{padding: '0 18px 18px'}}>No table cells were stored.</p> :
      <div className="table-wrap"><table className="data-table">
        <thead><tr>{headers.map(header => <th key={header.column_index}>{bilingualKhatauniLabel(header.label)}</th>)}</tr></thead>
        <tbody>{table.rows.map((row, rowNumber) => {
          const cellsByColumn = new Map((row.cells || []).map(cell => [cell.column_index, cell]));
          return <tr key={`${row.row_index}-${rowNumber}`}>{headers.map(header => {
            const cell = cellsByColumn.get(header.column_index);
            return <td key={header.column_index}>{cell ? <>
              <b>{display(cell.display_value || cell.final_value || cell.officer_value || cell.ai_value || cell.raw_ocr_value)}</b>
              {isPresent(cell.raw_ocr_value) && cell.raw_ocr_value !== cell.display_value ? <><br/><small>OCR: {cell.raw_ocr_value}</small></> : null}
              {cell.edited ? <><br/><small>Officer corrected</small></> : null}
            </> : '—'}</td>;
          })}</tr>;
        })}</tbody>
      </table></div>}
  </section>;
}

function LegacyExtraction({fields}) {
  if (!fields.length) return null;
  return <section className="card" style={{marginTop: 18}}>
    <div className="section-head"><div><h3>Legacy Extraction Evidence</h3><p>Retained for records digitized before document-native fields and tables were available.</p></div></div>
    <div className="table-wrap"><table className="data-table">
      <thead><tr><th>FIELD</th><th>AI VALUE</th><th>OFFICER / FINAL VALUE</th><th>CONFIDENCE</th></tr></thead>
      <tbody>{fields.map(field => <tr key={field.id || field.name}>
        <td>{label(field.name)}</td><td>{display(field.ai_value)}</td><td>{display(field.final_value || field.officer_value)}</td><td>{confidence(field.ai_confidence)}</td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}

function AuditTrail({auditTrail, digitizationAudit}) {
  const rows = [
    ...(auditTrail || []).map(item => ({...item, source: 'Workflow', actor: item.user_id, detail: item.metadata})),
    ...(digitizationAudit || []).map(item => ({
      ...item,
      source: 'Digitization',
      actor: item.actor_id,
      detail: item.after || item.metadata || item.before,
    })),
  ].sort((left, right) => new Date(right.timestamp || 0) - new Date(left.timestamp || 0));
  if (!rows.length) return <p className="muted" style={{padding: '0 18px 18px'}}>No audit events were stored.</p>;
  return <div className="table-wrap"><table className="data-table">
    <thead><tr><th>TIMESTAMP</th><th>SOURCE</th><th>ACTION</th><th>ACTOR</th><th>DETAIL</th></tr></thead>
    <tbody>{rows.map((item, index) => <tr key={`${item.source}-${item.id || index}`}>
      <td>{item.timestamp ? new Date(item.timestamp).toLocaleString() : '—'}</td>
      <td>{item.source}</td>
      <td>{item.action || '—'}{item.entity_type ? <><br/><small>{item.entity_type}</small></> : null}</td>
      <td>{item.actor || 'System'}</td>
      <td><small>{typeof item.detail === 'string' ? item.detail : item.detail ? JSON.stringify(item.detail) : '—'}</small></td>
    </tr>)}</tbody>
  </table></div>;
}

export default function Detail() {
  const {id} = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setData(null);
    setError('');
    api.record(id).then(setData).catch(result => setError(result.message));
  }, [id]);

  const digitized = useMemo(() => data?.digitized || {fields: [], tables: [], summary: {}}, [data]);
  if (!data) return error ? <ErrorMessage>{error}</ErrorMessage> : <Loader/>;

  const record = data.record || {};
  const document = data.document || {};
  const ocr = data.ocr || {};
  const summary = digitized.summary || {};
  const legacyPairs = [
    ['Owner name', record.owner_name],
    ['Father / guardian name', record.father_guardian_name],
    ['Khasra number', record.khasra_number],
    ['Khata number', record.khata_number],
    ['Area', record.area],
    ['Village', record.village],
    ['Tehsil', record.tehsil],
    ['District', record.district],
    ['State', record.state],
  ].filter(([, value]) => isPresent(value));

  return <>
    <div className="page-title"><div>
      <div className="eyebrow">VERIFIED DIGITAL KHATAUNI</div>
      <h2>{record.record_id}</h2>
      <p>Permanent Khatauni values retain the original OCR evidence and every officer correction.</p>
    </div><StatusBadge status={record.verification_status || 'VERIFIED'}/></div>
    <ErrorMessage>{error}</ErrorMessage>

    <section className="card">
      <div className="section-head"><div><h3>Verified Digital Khatauni</h3><p>Predefined Hindi headings with values originating only from OCR or officer verification.</p></div></div>
      <div className="review-meta">
        <div><span>HEADER FIELDS DETECTED</span>{summary.header_fields_detected || 0} / {summary.header_fields_total || 12}</div>
        <div><span>TABLE ROWS</span>{summary.rows_digitized || 0}</div>
        <div><span>OCR CELLS POPULATED</span>{summary.ocr_cells_populated || 0}</div>
        <div><span>VERIFICATION OFFICER</span>{record.verified_by || '—'}</div>
        <div><span>VERIFIED AT</span>{record.verified_at ? new Date(record.verified_at).toLocaleString() : '—'}</div>
      </div>
      <div className="section-head"><div><h3>Khatauni Header Fields</h3><p>Empty OCR matches remain visibly empty instead of receiving fallback values.</p></div></div>
      <DynamicFields fields={digitized.fields || []}/>
    </section>

    {(digitized.tables || []).map((table, index) => <DigitizedTable key={table.table_id || table.id || index} table={table} number={index + 1}/>) }

    {legacyPairs.length ? <section className="card" style={{marginTop: 18}}>
      <div className="section-head"><div><h3>Legacy Verified Summary</h3><p>Compatibility summary retained from the earlier fixed-record workflow.</p></div></div>
      <div className="review-meta">{legacyPairs.map(([name, value]) => <div key={name}><span>{name.toUpperCase()}</span>{display(value)}</div>)}</div>
    </section> : null}

    <div className="split" style={{marginTop: 18}}>
      <section className="card">
        <div className="section-head"><h3>Original Document</h3></div>
        {document.original ? <div className="document-preview">{document.original.toLowerCase().endsWith('.pdf') ? <iframe src={sourceUrl(document.original)} title="Original source PDF" style={{width:'100%',height:510,border:0}}/> : <img src={sourceUrl(document.original)} alt="Original source document"/>}</div> : <p className="muted" style={{padding: '0 18px 18px'}}>Original source file is unavailable.</p>}
        <div className="section-head"><h3>OpenCV-Enhanced Document</h3></div>
        {document.enhanced ? <div className="document-preview"><img src={sourceUrl(document.enhanced)} alt="OpenCV-enhanced source document"/></div> : <p className="muted" style={{padding: '0 18px 18px'}}>No enhanced image was stored.</p>}
      </section>
      <section className="card">
        <div className="section-head"><div><h3>Source Metadata</h3><p>Captured with the uploaded document.</p></div></div>
        <div className="review-meta">{[
          ['Filename', document.original_filename], ['Document type', document.document_type], ['State', document.state],
          ['District', document.district], ['Tehsil', document.tehsil], ['Village', document.village],
        ].map(([name, value]) => <div key={name}><span>{name.toUpperCase()}</span>{display(value)}</div>)}</div>
        <div className="section-head"><div><h3>Raw OCR Output</h3><p>{ocr.engine || 'OCR engine unavailable'}{ocr.languages ? ` · ${ocr.languages}` : ''}</p></div></div>
        <pre className="raw-ocr-text">{ocr.raw_text || 'No OCR text stored.'}</pre>
      </section>
    </div>

    <LegacyExtraction fields={ocr.fields || []}/>
    <section className="card" style={{marginTop: 18}}>
      <div className="section-head"><div><h3>Audit Trail</h3><p>Workflow events and document-native field/table corrections are retained separately.</p></div></div>
      <AuditTrail auditTrail={data.audit_trail} digitizationAudit={data.digitization_audit}/>
    </section>
  </>;
}
