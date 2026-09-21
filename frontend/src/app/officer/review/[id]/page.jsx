'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { AlertTriangle, CheckCircle, Clipboard, Download, FileText, Minus, Plus, RefreshCw, Save, ScanLine, Search, Trash2, XCircle, ZoomIn } from 'lucide-react';
import { API_URL, api } from '../../../../lib/api';
import { bilingualKhatauniLabel } from '../../../../lib/khatauniLabels';
import { activityLabel } from '../../../../lib/activity';
import { Button, ErrorMessage, Loader, StatusBadge } from '../../../../components/common/UI';
import ConfidenceBadge from '../../../../components/officer/ConfidenceBadge';

const sourceUrl = (path) => path ? `${API_URL}/uploads/${path.split(/[\\/]/).pop()}` : '';
const valueOf = (entry) => entry?.officer_value ?? entry?.final_value ?? entry?.ai_value ?? entry?.raw_ocr_value ?? '';
const ocrValueOf = (entry) => entry?.raw_ocr_value ?? entry?.ai_value ?? '';
const recognitionOf = (entry) => entry?.audit_metadata?.recognition_evidence || {};

function RecognitionEvidence({ entry }) {
  const evidence = recognitionOf(entry);
  const warnings = Array.isArray(evidence.warnings) ? evidence.warnings : [];
  const disagreement = warnings.includes('engine_disagreement') || warnings.includes('tesseract_digit_disagreement');
  if (!evidence.selected_engine && !disagreement) return null;
  return <details className="recognition-details developer-only">
    <summary>Recognition Details</summary>
    <div>
      {evidence.selected_engine && <span>Selected recognizer: {evidence.selected_engine}</span>}
      {disagreement && <span><AlertTriangle size={11} /> Candidate readings differ; review suggested.</span>}
      {evidence.confidence != null && <span>OCR confidence: {Math.round(evidence.confidence)}%</span>}
    </div>
  </details>;
}

function normalizeDigitization(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const table = Array.isArray(payload?.tables) ? payload.tables[0] : null;
  if (!table) return { items, table: null, summary: payload?.summary || {} };
  const headerSource = table.final_headers?.length ? table.final_headers : table.officer_headers?.length ? table.officer_headers : table.detected_headers || [];
  const headers = headerSource.map((label, index) => ({ label: typeof label === 'string' ? label : label?.label || '', column_index: index }));
  const cells = Array.isArray(table.cells) ? table.cells : [];
  const indices = [...new Set(cells.map((cell) => cell.row_index))].sort((a, b) => a - b);
  const rows = indices.map((rowIndex) => ({ row_index: rowIndex, cells: cells.filter((cell) => cell.row_index === rowIndex) }));
  return { items, table: { ...table, headers, rows }, summary: payload?.summary || {} };
}

function confidenceLabel(value) {
  if (value === null || value === undefined) return 'उपलब्ध नहीं';
  if (value >= 90) return 'उच्च विश्वास';
  if (value >= 70) return 'मध्यम विश्वास';
  return 'कम विश्वास';
}

function SourceDocument({ document, processedPath, sourceMode, setSourceMode, zoom, setZoom, fit, setFit }) {
  const selectedPath = sourceMode === 'enhanced' && processedPath ? processedPath : document?.file_path;
  const isPdf = selectedPath?.toLowerCase().endsWith('.pdf');
  return <section className="card evidence-pane">
    <div className="section-head evidence-head">
      <div><div className="eyebrow">SOURCE RECORD</div><h3>Source Record</h3><p>Compare the original record with its structured digital version.</p></div>
      <div className="evidence-toolbar">
        <button className={sourceMode === 'original' ? 'active' : ''} onClick={() => setSourceMode('original')} type="button">Original</button>
        <button className={sourceMode === 'enhanced' ? 'active' : ''} onClick={() => setSourceMode('enhanced')} disabled={!processedPath} type="button">Enhanced</button>
        <button onClick={() => { setFit(false); setZoom((value) => Math.min(2.5, value + .2)); }} type="button" aria-label="Zoom in"><ZoomIn size={14} /></button>
        <button onClick={() => { setFit(false); setZoom((value) => Math.max(.4, value - .2)); }} type="button" aria-label="Zoom out"><Minus size={14} /></button>
        <button onClick={() => { setFit(true); setZoom(1); }} type="button">Fit</button>
        <button onClick={() => { setFit(false); setZoom(1); }} type="button">Reset</button>
      </div>
    </div>
    <div className={`source-canvas ${fit ? 'fit' : ''}`}>
      {selectedPath ? (isPdf ? <iframe src={sourceUrl(selectedPath)} title="Original uploaded PDF" /> : <img src={sourceUrl(selectedPath)} alt="Actual uploaded Khatauni" style={{ transform: `scale(${zoom})` }} />) : <FileText size={46} />}
    </div>
  </section>;
}

function DigitalKhatauni({ digitization, work, onFieldChange, onCellChange, onAddRow, onDeleteRow }) {
  const { items, table } = digitization;
  return <section className="card khatauni-pane">
    <div className="section-head"><div><div className="eyebrow">DIGITAL KHATAUNI</div><h3>Digital Khatauni</h3><p>Review and correct the structured record beside the source document.</p></div></div>
    <div className="khatauni-fields">
      {items.length ? items.map((field) => <label className="khatauni-field" key={field.id}>
        <span>{bilingualKhatauniLabel(field.original_label)}</span>
        <input key={`${field.id}-${valueOf(field)}`} defaultValue={valueOf(field)} placeholder="स्वचालित रूप से पता नहीं चला / Not automatically detected" onBlur={(event) => event.target.value !== String(valueOf(field)) && onFieldChange(field, event.target.value)} disabled={Boolean(work)} />
        <small><ConfidenceBadge value={field.ai_confidence} source={field.confidence_source} /></small>
        <RecognitionEvidence entry={field} />
        {field.officer_value !== null && field.officer_value !== undefined && <em>OCR: {ocrValueOf(field) || 'रिक्त / Blank'} · अधिकारी सुधार सुरक्षित / Officer correction saved</em>}
      </label>) : <div className="khatauni-empty">Extract Khatauni Data to create the empty schema and populate OCR matches.</div>}
    </div>
    <div className="khatauni-table-head"><div><b>मुख्य खतौनी तालिका / Main Khatauni Table</b><small>Rows originate from OCR; manual rows are explicitly marked.</small></div><Button variant="secondary" onClick={onAddRow} disabled={!table?.id || Boolean(work)}><Plus size={14} /> पंक्ति जोड़ें / Add Row</Button></div>
    {table ? <div className="table-wrap khatauni-table-wrap"><table className="data-table khatauni-table">
      <thead><tr>{table.headers.map((header) => <th key={header.column_index}>{bilingualKhatauniLabel(header.label)}</th>)}<th>स्थिति / Status</th></tr></thead>
      <tbody>{table.rows.length ? table.rows.map((row) => {
        const manual = row.cells.length > 0 && row.cells.every((cell) => cell.confidence_source === 'officer_manual');
        return <tr key={row.row_index}>{table.headers.map((header) => {
          const cell = row.cells.find((candidate) => candidate.column_index === header.column_index);
          return <td key={header.column_index}>{cell ? <div className="khatauni-cell"><input key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} placeholder="मान दर्ज करें / Enter Value" onBlur={(event) => event.target.value !== String(valueOf(cell)) && onCellChange(cell, event.target.value)} disabled={Boolean(work)} /><ConfidenceBadge value={cell.ai_confidence} source={cell.confidence_source} /><RecognitionEvidence entry={cell} />{cell.officer_value !== null && cell.officer_value !== undefined && <small>OCR: {ocrValueOf(cell) || 'रिक्त / Blank'}</small>}</div> : <span className="empty-cell">रिक्त / Blank</span>}</td>;
        })}<td><span className={`source-tag ${manual ? 'manual' : 'ocr'}`}>{manual ? 'अधिकारी द्वारा जोड़ा गया / Added by Officer' : 'OCR'}</span><button className="table-delete-button" type="button" onClick={() => onDeleteRow(row)} disabled={Boolean(work)}><Trash2 size={13} /> Delete row</button></td></tr>;
      }) : <tr><td colSpan={table.headers.length + 1} className="dynamic-empty-row">कोई पंक्ति विश्वसनीय रूप से नहीं मिली। सही पंक्ति अधिकारी जोड़ सकते हैं। / No row was detected reliably. An officer can add the correct row.</td></tr>}</tbody>
    </table></div> : <div className="khatauni-empty">No Khatauni table has been extracted yet.</div>}
  </section>;
}

export default function Review() {
  const { id } = useParams();
  const router = useRouter();
  const query = useSearchParams();
  const [submission, setSubmission] = useState(null);
  const [ocr, setOcr] = useState(null);
  const [digitization, setDigitization] = useState({ items: [], table: null, summary: {} });
  const [processedPath, setProcessedPath] = useState('');
  const [audits, setAudits] = useState([]);
  const [sourceMode, setSourceMode] = useState('original');
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState(true);
  const [work, setWork] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reasonCategory, setReasonCategory] = useState('');
  const [officerNote, setOfficerNote] = useState('');
  const hasRawOcr = Boolean(ocr?.raw_text?.trim());
  const hasExtraction = digitization.items.length > 0 && Boolean(digitization.table);
  const summary = digitization.summary || {};
  const tokenRows = Array.isArray(ocr?.tokens) ? ocr.tokens : [];

  async function refreshDigitization() { setDigitization(normalizeDigitization(await api.digitization(id))); }
  async function refreshAudits() { const rows = await api.audit(); setAudits((Array.isArray(rows) ? rows : []).filter((row) => String(row.document_id) === String(id)).slice(0, 20)); }

  useEffect(() => {
    let active = true;
    Promise.all([api.submissions(), api.latestOcr(id).catch(() => null), api.digitization(id).catch(() => null), api.audit().catch(() => [])])
      .then(([submissions, latestOcr, structure, auditRows]) => {
        if (!active) return;
        const found = submissions.find((row) => String(row.document_id) === String(id));
        if (!found) throw new Error('Submission not found');
        setSubmission(found);
        if (latestOcr) { setOcr(latestOcr); setProcessedPath(latestOcr.processed_image_path || ''); }
        if (structure) setDigitization(normalizeDigitization(structure));
        setAudits(auditRows.filter((row) => String(row.document_id) === String(id)).slice(0, 20));
      }).catch((loadError) => active && setError(loadError.message));
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    if (query.get('reject_duplicate') !== '1') return;
    const record = query.get('record');
    setReasonCategory('Duplicate Submission');
    setOfficerNote(record ? `This submission exactly matches existing verified record ${record}.` : 'This submission exactly matches an existing record.');
    setRejectOpen(true);
  }, [query]);

  async function execute(kind) {
    if (work) return;
    setWork(kind); setError(''); setNotice('');
    try {
      if (kind === 'preprocess') {
        const result = await api.preprocess(id); setProcessedPath(result.processed_file_path); setSourceMode('enhanced'); setOcr(null); setDigitization({ items: [], table: null, summary: {} }); setNotice('OpenCV preprocessing completed. Enhanced evidence is ready.');
      } else if (kind === 'ocr') {
        const result = await api.ocr(id, processedPath); setOcr(result); setDigitization({ items: [], table: null, summary: {} });
        if (result.status !== 'COMPLETED') throw new Error(result.message || 'Document recognition could not process this record.');
        setNotice('Document recognition completed. Technical evidence is available below.');
      } else if (kind === 'extract') {
        const result = await api.extract(id, ocr?.ocr_id); setDigitization(normalizeDigitization(result)); setNotice(result.message || 'Khatauni extraction completed.');
      }
      await refreshAudits();
    } catch (actionError) { setError(actionError.message); } finally { setWork(''); }
  }

  async function mutate(key, action, message) {
    if (work) return;
    setWork(key); setError('');
    try { await action(); await refreshDigitization(); await refreshAudits(); setNotice(message); } catch (mutationError) { setError(mutationError.message); } finally { setWork(''); }
  }

  const updateField = (field, value) => mutate(`field-${field.id}`, () => api.updateDynamicField(id, field.id, { officer_value: value }), 'Officer correction saved; original OCR remains preserved.');
  const updateCell = (cell, value) => mutate(`cell-${cell.id}`, () => api.updateDynamicTableCell(id, digitization.table.id, cell.id, { officer_value: value }), 'Table correction saved; original OCR remains preserved.');
  const addRow = () => mutate('add-row', () => api.createDynamicTableRow(id, digitization.table.id, {}), 'Manual Khatauni row added and audited.');
  const deleteRow = (row) => { if (confirm(`Remove row ${row.row_index + 1}?`)) mutate('delete-row', () => api.deleteDynamicTableRow(id, digitization.table.id, row.row_index), 'Khatauni row removed and audited.'); };

  async function decide(action, rejection) {
    if (work) return;
    if (!confirm(`Confirm ${action.replace('-', ' ')} for this document?`)) return;
    setWork(action); setError('');
    try { await api.decision(id, action, rejection); router.push(action === 'approve' ? '/officer/records' : '/officer/submissions'); } catch (decisionError) { setError(decisionError.message); setWork(''); }
  }

  async function copyRaw() { await navigator.clipboard.writeText(ocr?.raw_text || ''); setNotice('Raw OCR copied to clipboard.'); }
  function downloadRaw() { const blob = new Blob([ocr?.raw_text || ''], { type: 'text/plain;charset=utf-8' }); const url = URL.createObjectURL(blob); const link = window.document.createElement('a'); link.href = url; link.download = `document-${id}-tesseract-ocr.txt`; link.click(); URL.revokeObjectURL(url); }

  if (!submission) return error ? <ErrorMessage>{error}</ErrorMessage> : <Loader label="Loading Khatauni review workspace…" />;
  const sourceDocument = submission.document;
  const isRejected = submission.status === 'REJECTED';
  const steps = [['1. Document Upload', Boolean(sourceDocument?.file_path)], ['2. OpenCV Preprocessing', Boolean(processedPath)], ['3. Tesseract OCR', Boolean(ocr)], ['4. Data Extraction', hasExtraction], ['5. Officer Verification', submission.status === 'VERIFIED'], ['6. Digital Record', submission.status === 'VERIFIED']];
  const currentStep = steps.findIndex((step) => !step[1]);

  return <>
    <div className="page-title"><div><div className="eyebrow">VERIFICATION WORKSPACE</div><h2>Land Record #{sourceDocument.id}</h2><p>{sourceDocument.original_filename} · {sourceDocument.file_size ? `${(sourceDocument.file_size / 1024).toFixed(1)} KB` : 'file size unavailable'} · Uploaded {new Date(sourceDocument.uploaded_at || submission.submitted_at).toLocaleString()}</p><p>Uploader: {submission.user?.name} ({submission.user?.email})</p></div><StatusBadge status={submission.status} /></div>
    <ErrorMessage>{error}</ErrorMessage>{notice && <div className="notice success" role="status">{notice}</div>}{work.startsWith('field-') || work.startsWith('cell-') ? <div className="notice" role="status">Saving correction…</div> : null}{isRejected && <div className="notice warn"><b>Rejected record — read-only.</b><br/>Reason: {submission.rejection?.reason_category || 'Unavailable'}{submission.rejection?.officer_note && <><br/>{submission.rejection.officer_note}</>}</div>}
    <section className="card khatauni-stepper" aria-label="Document processing progress"><ol>{steps.map(([label, done], index) => <li className={done ? 'complete' : (index === currentStep ? 'current' : '')} key={label}><span aria-hidden="true">{done ? '✓' : index + 1}</span><b>{label}</b></li>)}</ol></section>
    <div className="review-workbench"><SourceDocument document={sourceDocument} processedPath={processedPath} sourceMode={sourceMode} setSourceMode={setSourceMode} zoom={zoom} setZoom={setZoom} fit={fit} setFit={setFit} /><DigitalKhatauni digitization={digitization} work={isRejected ? 'read-only' : work} onFieldChange={updateField} onCellChange={updateCell} onAddRow={addRow} onDeleteRow={deleteRow} /></div>

    {!isRejected && <section className="card processing-card"><div className="section-head"><div><div className="eyebrow">DOCUMENT PROCESSING</div><h3>Prepare the digital record</h3><p>Process this source record before reviewing its structured data.</p></div><div className="actions"><Button variant="secondary" onClick={() => execute('preprocess')} loading={work === 'preprocess'} disabled={Boolean(work)}><ScanLine size={15} /> Preprocess</Button><Button onClick={() => execute('ocr')} loading={work === 'ocr'} disabled={!processedPath || Boolean(work)}><Search size={15} /> Run OCR</Button><Button variant="secondary" onClick={() => execute('extract')} loading={work === 'extract'} disabled={!hasRawOcr || Boolean(work)}>Extract Data</Button><Button variant="secondary" onClick={async () => { await refreshDigitization(); setNotice('All corrections are persisted as they are entered.'); }} disabled={!hasExtraction || Boolean(work)}><Save size={15} /> Save Corrections</Button></div></div>
      {work === 'ocr' && <div className="ocr-live-state"><span className="ocr-live-spinner" /><b>Running OCR on the actual document with Tesseract hin+eng…</b></div>}{work === 'extract' && <div className="ocr-live-state"><span className="ocr-live-spinner" /><b>Extracting Khatauni structure from OCR tokens…</b></div>}
    </section>}

    <section className="card raw-ocr-card developer-only"><div className="section-head"><div><div className="eyebrow">TECHNICAL EVIDENCE</div><h3>Raw OCR output</h3><p>Unmodified recognition output and token details for diagnostics.</p></div><div className="actions"><Button variant="secondary" onClick={copyRaw} disabled={!ocr}><Clipboard size={14} /> Copy Raw OCR</Button><Button variant="secondary" onClick={downloadRaw} disabled={!ocr}><Download size={14} /> Download OCR Text</Button></div></div>
      <div className="ocr-evidence-meta"><div><span>ENGINE</span><b>{ocr?.engine || 'Not run'}</b></div><div><span>LANGUAGES</span><b>Hindi + English ({ocr?.languages || 'hin+eng'})</b></div><div><span>STATUS</span><b>{ocr?.status || 'Not run'}</b></div><div><span>CHARACTERS</span><b>{ocr?.character_count ?? '—'}</b></div><div><span>TOKENS</span><b>{ocr?.token_count ?? '—'}</b></div><div><span>OVERALL CONFIDENCE</span><b>{ocr?.overall_confidence == null ? 'Unavailable' : `${ocr.overall_confidence.toFixed(2)}%`}</b></div></div>
      <div className="raw-ocr-label">================ RAW OCR TEXT ================</div><pre className="raw-ocr-text">{ocr ? (ocr.raw_text || 'OCR_FAILED — Tesseract returned no readable text.') : 'Run Real OCR to display the exact Tesseract output.'}</pre>
      <details className="token-evidence"><summary>OCR Evidence — token coordinates and confidence ({tokenRows.length})</summary><div className="table-wrap"><table className="data-table"><thead><tr><th>TOKEN</th><th>CONFIDENCE</th><th>X</th><th>Y</th><th>WIDTH</th><th>HEIGHT</th><th>LINE</th><th>BLOCK</th><th>PAGE</th></tr></thead><tbody>{tokenRows.map((token) => <tr key={token.index}><td>{token.text}</td><td>{token.confidence == null ? '—' : `${token.confidence.toFixed(1)}%`}</td><td>{token.bbox?.left}</td><td>{token.bbox?.top}</td><td>{token.bbox?.width}</td><td>{token.bbox?.height}</td><td>{token.line_num}</td><td>{token.block_num}</td><td>{token.page_num}</td></tr>)}</tbody></table></div></details>
    </section>

    <section className="card extraction-summary-card developer-only"><div className="section-head"><div><div className="eyebrow">TECHNICAL SUMMARY</div><h3>Extraction diagnostics</h3></div></div><div className="extraction-summary-grid"><div><span>HEADER FIELDS</span><b>{summary.header_fields_detected || 0} / {summary.header_fields_total || 12}</b></div><div><span>TABLE ROWS</span><b>{summary.rows_digitized || 0}</b></div><div><span>OCR CELLS POPULATED</span><b>{summary.ocr_cells_populated || 0}</b></div><div><span>HIGH</span><b>{summary.high_confidence_items || 0}</b></div><div><span>MEDIUM</span><b>{summary.medium_confidence_items || 0}</b></div><div><span>LOW</span><b>{summary.low_confidence_items || 0}</b></div><div><span>UNAVAILABLE</span><b>{summary.unavailable_confidence_items || 0}</b></div></div></section>
    <section className="card review-audit-card"><div className="section-head"><div><div className="eyebrow">ACTIVITY</div><h3>Record history</h3></div><Button variant="secondary" onClick={refreshAudits}><RefreshCw size={14} /> Refresh</Button></div><div className="table-wrap"><table className="data-table"><thead><tr><th>TIME</th><th>ACTION</th><th>ACTOR</th><th className="developer-only">RAW EVENT</th><th className="developer-only">TECHNICAL DETAILS</th></tr></thead><tbody>{audits.length ? audits.map((row) => <tr key={row.id}><td>{new Date(row.timestamp).toLocaleString()}</td><td>{activityLabel(row.action)}</td><td>{row.user_id ? `Account #${row.user_id}` : 'System'}</td><td className="developer-only">{row.action}</td><td className="developer-only"><code>{row.metadata_json || '—'}</code></td></tr>) : <tr><td colSpan="5">No lifecycle events yet.</td></tr>}</tbody></table></div></section>
    {!isRejected && <section className="card final-decision"><div className="section-head"><div><h3>Officer decision</h3><p>Compare the source and structured values before recording a decision.</p></div><div className="actions"><Button onClick={() => decide('approve')} loading={work === 'approve'} loadingText="Verifying…" disabled={!hasExtraction || Boolean(work)}><CheckCircle size={15} /> Approve & Verify</Button><Button variant="secondary" onClick={() => decide('mark-review')} loading={work === 'mark-review'} loadingText="Updating…" disabled={Boolean(work)}><AlertTriangle size={15} /> Needs Review</Button><Button variant="danger" onClick={() => setRejectOpen(true)} loading={work === 'reject'} disabled={Boolean(work)}><XCircle size={15} /> Reject</Button></div></div></section>}
    {rejectOpen && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="reject-title"><div className="modal-card"><h3 id="reject-title">Reject record</h3><p>Choose a meaningful reason before confirming. This is saved in the audit trail and shown to the submitting citizen.</p><div className="field"><label>Reason Category</label><select value={reasonCategory} onChange={event => setReasonCategory(event.target.value)}><option value="">Select a reason</option>{['Poor Scan Quality', 'Incomplete Document', 'Incorrect Document', 'Unreadable Information', 'Duplicate Submission', 'Information Mismatch', 'Other'].map(reason => <option key={reason}>{reason}</option>)}</select></div><div className="field"><label>Officer Note {reasonCategory === 'Other' ? '(required)' : '(optional)'}</label><textarea value={officerNote} onChange={event => setOfficerNote(event.target.value)} placeholder="Explain what the citizen needs to correct."/></div><div className="actions" style={{marginTop: 16}}><Button variant="secondary" onClick={() => setRejectOpen(false)}>Cancel</Button><Button variant="danger" disabled={!reasonCategory || (reasonCategory === 'Other' && !officerNote.trim())} onClick={() => { setRejectOpen(false); decide('reject', {reason_category: reasonCategory, officer_note: officerNote.trim() || null}); }}>Confirm rejection</Button></div></div></div>}
  </>;
}
