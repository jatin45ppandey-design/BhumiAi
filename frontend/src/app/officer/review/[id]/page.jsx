'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AlertTriangle, CheckCircle, FileText, Minus, Plus, Save, ScanLine, Search, Trash2, XCircle, ZoomIn } from 'lucide-react';
import { api } from '../../../../lib/api';
import { bilingualKhatauniLabel } from '../../../../lib/khatauniLabels';
import { Button, ErrorMessage, Loader, StatusBadge, Toast } from '../../../../components/common/UI';
import ConfidenceBadge, { ValidationBadge } from '../../../../components/officer/ConfidenceBadge';
import AuthenticatedDocument from '../../../../components/documents/AuthenticatedDocument';

const valueOf = (entry) => entry?.officer_value ?? entry?.final_value ?? entry?.ai_value ?? entry?.raw_ocr_value ?? '';
const ocrValueOf = (entry) => entry?.raw_ocr_value ?? entry?.ai_value ?? '';
const validationOf = (entry) => entry?.validation ?? entry?.audit_metadata?.validation;
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

function SourceDocument({ document, processedPath, sourceMode, setSourceMode, zoom, setZoom, fit, setFit }) {
  const selectedPath = sourceMode === 'enhanced' && processedPath ? processedPath : document?.file_path;
  const isPdf = selectedPath?.toLowerCase().endsWith('.pdf');
  const variant = sourceMode === 'enhanced' && processedPath ? 'processed' : 'original';
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
      {selectedPath ? <AuthenticatedDocument documentId={document.id} variant={variant} isPdf={isPdf} title="Original uploaded PDF" alt="Actual uploaded Khatauni" style={isPdf ? undefined : { transform: `scale(${zoom})` }}/> : <FileText size={46} />}
    </div>
  </section>;
}

function ExactDuplicateReview({match, onContinue, onReject}) {
  if (!match?.duplicate) return null;
  const verified = Boolean(match.verified_record_id);
  return <section className="card duplicate-review-card">
    <div className="section-head"><div><div className="eyebrow">EXACT DOCUMENT MATCH DETECTED</div><h3>Officer duplicate review</h3><p>This SHA-256 match is decision support only. It does not change the submission automatically.</p></div></div>
    <div className="review-meta"><div><span>EXISTING SUBMISSION</span>{match.matched_submission_id ? `#${match.matched_submission_id}` : 'Unavailable'}</div><div><span>STATUS</span>{match.matched_status || 'Unavailable'}</div><div><span>VERIFIED RECORD</span>{match.verified_record_code ? `${match.verified_record_code} (#${match.verified_record_id})` : 'No verified record'}</div><div><span>VERIFIED AT</span>{match.verified_at ? new Date(match.verified_at).toLocaleString() : 'Not verified'}</div></div>
    <div className="actions" style={{padding: '0 20px 20px'}}>{verified && <Button variant="secondary" onClick={() => window.location.assign(`/officer/records/${match.verified_record_id}`)}>View Existing Record</Button>}<Button variant="secondary" onClick={onContinue}>Continue Review</Button>{verified && <Button variant="danger" onClick={onReject}>Reject as Duplicate</Button>}</div>
  </section>;
}

function DigitalKhatauni({ digitization, digitizationLoading, work, onFieldChange, onCellChange, onAddRow, onDeleteRow }) {
  const { items, table } = digitization;
  if (digitizationLoading) return <section className="card khatauni-pane khatauni-loading" aria-label="Loading structured record"><div className="section-head"><div><div className="eyebrow">DIGITAL KHATAUNI</div><h3>Loading structured record…</h3><p>The source record remains available while extracted fields load.</p></div></div><div className="khatauni-fields"><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/></div><div className="skeleton-block skeleton-khatauni-table"/></section>;
  return <section className="card khatauni-pane">
    <div className="section-head"><div><div className="eyebrow">DIGITAL KHATAUNI</div><h3>Digital Khatauni</h3><p>Review and correct the structured record beside the source document.</p></div></div>
    <div className="khatauni-fields">
      {items.length ? items.map((field) => <label className="khatauni-field" key={field.id}>
        <span>{bilingualKhatauniLabel(field.original_label)}</span>
        <input key={`${field.id}-${valueOf(field)}`} defaultValue={valueOf(field)} placeholder="स्वचालित रूप से पता नहीं चला / Not automatically detected" onBlur={(event) => event.target.value !== String(valueOf(field)) && onFieldChange(field, event.target.value)} disabled={Boolean(work)} />
        <small className="recognition-indicators"><ConfidenceBadge value={field.ai_confidence} /><ValidationBadge validation={validationOf(field)} /></small>
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
          return <td key={header.column_index}>{cell ? <div className="khatauni-cell"><input key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} placeholder="मान दर्ज करें / Enter Value" onBlur={(event) => event.target.value !== String(valueOf(cell)) && onCellChange(cell, event.target.value)} disabled={Boolean(work)} /><span className="recognition-indicators"><ConfidenceBadge value={cell.ai_confidence} /><ValidationBadge validation={validationOf(cell)} /></span>{cell.officer_value !== null && cell.officer_value !== undefined && <small>OCR: {ocrValueOf(cell) || 'रिक्त / Blank'}</small>}</div> : <span className="empty-cell">रिक्त / Blank</span>}</td>;
        })}<td><span className={`source-tag ${manual ? 'manual' : 'ocr'}`}>{manual ? 'अधिकारी द्वारा जोड़ा गया / Added by Officer' : 'OCR'}</span><button className="table-delete-button" type="button" onClick={() => onDeleteRow(row)} disabled={Boolean(work)}><Trash2 size={13} /> Delete row</button></td></tr>;
      }) : <tr><td colSpan={table.headers.length + 1} className="dynamic-empty-row">कोई पंक्ति विश्वसनीय रूप से नहीं मिली। सही पंक्ति अधिकारी जोड़ सकते हैं। / No row was detected reliably. An officer can add the correct row.</td></tr>}</tbody>
    </table></div> : <div className="khatauni-empty">No Khatauni table has been extracted yet.</div>}
  </section>;
}

export default function Review() {
  const { id } = useParams();
  const router = useRouter();
  const [submission, setSubmission] = useState(null);
  const [ocr, setOcr] = useState(null);
  const [digitization, setDigitization] = useState({ items: [], table: null, summary: {} });
  const [digitizationLoading, setDigitizationLoading] = useState(true);
  const [processedPath, setProcessedPath] = useState('');
  const [sourceMode, setSourceMode] = useState('original');
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState(true);
  const [work, setWork] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [rejectOpen, setRejectOpen] = useState(false);
  const [pendingDecision, setPendingDecision] = useState('');
  const [pendingDeleteRow, setPendingDeleteRow] = useState(null);
  const [reasonCategory, setReasonCategory] = useState('');
  const [officerNote, setOfficerNote] = useState('');
  const [duplicate, setDuplicate] = useState(null);
  const hasRawOcr = Boolean(ocr?.raw_text?.trim());
  const hasExtraction = digitization.items.length > 0 && Boolean(digitization.table);

  async function refreshDigitization() { setDigitization(normalizeDigitization(await api.digitization(id))); }

  useEffect(() => {
    let active = true;
    api.submissions().then(async (submissions) => {
      if (!active) return;
      const found = submissions.find((row) => String(row.document_id) === String(id));
      if (!found) throw new Error('Submission not found');
      setSubmission(found);
      if (!['VERIFIED', 'REJECTED'].includes(found.status)) {
        const result = await api.duplicateCheck(id);
        if (active) setDuplicate(result);
      }
    }).catch((loadError) => active && setError(loadError.message));
    api.latestOcr(id).then((latestOcr) => {
      if (active && latestOcr) { setOcr(latestOcr); setProcessedPath(latestOcr.processed_image_path || ''); }
    }).catch(() => {});
    api.digitization(id).then((structure) => {
      if (active && structure) setDigitization(normalizeDigitization(structure));
    }).catch(() => {}).finally(() => active && setDigitizationLoading(false));
    return () => { active = false; };
  }, [id]);

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
    } catch (actionError) { setError(actionError.message); } finally { setWork(''); }
  }

  async function mutate(key, action, message) {
    if (work) return;
    setWork(key); setError('');
    try { await action(); await refreshDigitization(); setNotice(message); } catch (mutationError) { setError(mutationError.message); } finally { setWork(''); }
  }

  const updateField = (field, value) => mutate(`field-${field.id}`, () => api.updateDynamicField(id, field.id, { officer_value: value }), 'Officer correction saved; original OCR remains preserved.');
  const updateCell = (cell, value) => mutate(`cell-${cell.id}`, () => api.updateDynamicTableCell(id, digitization.table.id, cell.id, { officer_value: value }), 'Table correction saved; original OCR remains preserved.');
  const addRow = () => mutate('add-row', () => api.createDynamicTableRow(id, digitization.table.id, {}), 'Manual Khatauni row added and audited.');
  const deleteRow = row => setPendingDeleteRow(row);
  async function saveCorrections() {
    if (work) return;
    setWork('save-corrections'); setError('');
    try { await refreshDigitization(); setNotice('Corrections refreshed; original OCR remains preserved.'); } catch (saveError) { setError(saveError.message); } finally { setWork(''); }
  }

  async function decide(action, rejection) {
    if (work) return;
    if (action === 'reject') setRejectOpen(true);
    else setPendingDecision(action);
    setWork(action); setError('');
    try { await api.decision(id, action, rejection); router.push(action === 'approve' ? '/officer/records' : '/officer/submissions'); } catch (decisionError) { setError(decisionError.message); setWork(''); }
  }

  async function continueDuplicateReview() {
    if (!duplicate?.matched_document_id || work) return;
    setWork('duplicate-continue'); setError('');
    try {
      await api.duplicateContinue(id, duplicate.matched_document_id);
      setDuplicate(null);
      setNotice('Duplicate review recorded. The submission remains active.');
    } catch (duplicateError) { setError(duplicateError.message); }
    finally { setWork(''); }
  }

  function rejectAsDuplicate() {
    setReasonCategory('Duplicate Submission');
    setOfficerNote(duplicate?.verified_record_code ? `This submission exactly matches existing verified record ${duplicate.verified_record_code}.` : 'This submission exactly matches an existing verified record.');
    setRejectOpen(true);
  }

  if (!submission) return error ? <ErrorMessage>{error}</ErrorMessage> : <Loader label="Loading Khatauni review workspace…" />;
  const sourceDocument = submission.document;
  const isRejected = submission.status === 'REJECTED';
  const isVerified = submission.status === 'VERIFIED';
  const isTerminal = isRejected || isVerified;
  const steps = [['1. Document Upload', Boolean(sourceDocument?.file_path)], ['2. OpenCV Preprocessing', Boolean(processedPath)], ['3. Tesseract OCR', Boolean(ocr)], ['4. Data Extraction', hasExtraction], ['5. Officer Verification', submission.status === 'VERIFIED'], ['6. Digital Record', submission.status === 'VERIFIED']];
  const currentStep = steps.findIndex((step) => !step[1]);

  return <>
    <div className="page-title"><div><div className="eyebrow">VERIFICATION WORKSPACE</div><h2>Land Record #{sourceDocument.id}</h2><p>{sourceDocument.original_filename} · {sourceDocument.file_size ? `${(sourceDocument.file_size / 1024).toFixed(1)} KB` : 'file size unavailable'} · Uploaded {new Date(sourceDocument.uploaded_at || submission.submitted_at).toLocaleString()}</p><p>Uploader: {submission.user?.name} ({submission.user?.email})</p></div><StatusBadge status={submission.status} /></div>
    <ErrorMessage>{error}</ErrorMessage><Toast message={notice} onDismiss={() => setNotice('')}/>{work.startsWith('field-') || work.startsWith('cell-') ? <div className="notice" role="status">Saving correction…</div> : null}{isRejected && <div className="notice warn"><b>Rejected record — read-only.</b><br/>Reason: {submission.rejection?.reason_category || 'Unavailable'}{submission.rejection?.officer_note && <><br/>{submission.rejection.officer_note}</>}</div>}{isVerified && <div className="notice"><b>Verified record — read-only.</b><br/>Open the permanent verified record to review or export it.</div>}
    <section className="card khatauni-stepper" aria-label="Document processing progress"><ol>{steps.map(([label, done], index) => <li className={done ? 'complete' : (index === currentStep ? 'current' : '')} key={label}><span aria-hidden="true">{done ? '✓' : index + 1}</span><b>{label}</b></li>)}</ol></section>
    {!isTerminal && <ExactDuplicateReview match={duplicate} onContinue={continueDuplicateReview} onReject={rejectAsDuplicate}/>}
    <div className="review-workbench"><SourceDocument document={sourceDocument} processedPath={processedPath} sourceMode={sourceMode} setSourceMode={setSourceMode} zoom={zoom} setZoom={setZoom} fit={fit} setFit={setFit} /><DigitalKhatauni digitization={digitization} digitizationLoading={digitizationLoading} work={isRejected ? 'read-only' : work} onFieldChange={updateField} onCellChange={updateCell} onAddRow={addRow} onDeleteRow={deleteRow} /></div>

    {!isTerminal && <section className="card processing-card"><div className="section-head"><div><div className="eyebrow">DOCUMENT PROCESSING</div><h3>Prepare the digital record</h3><p>Process this source record before reviewing its structured data.</p></div><div className="actions"><Button variant="secondary" onClick={() => execute('preprocess')} loading={work === 'preprocess'} disabled={Boolean(work)}><ScanLine size={15} /> Preprocess</Button><Button onClick={() => execute('ocr')} loading={work === 'ocr'} disabled={!processedPath || Boolean(work)}><Search size={15} /> Run OCR</Button><Button variant="secondary" onClick={() => execute('extract')} loading={work === 'extract'} disabled={!hasRawOcr || Boolean(work)}>Extract Data</Button><Button variant="secondary" onClick={saveCorrections} loading={work === 'save-corrections'} loadingText="Saving Corrections…" disabled={!hasExtraction || Boolean(work)}><Save size={15} /> Save Corrections</Button></div></div>
      {work === 'ocr' && <div className="ocr-live-state"><span className="ocr-live-spinner" /><b>Running OCR on the actual document with Tesseract hin+eng…</b></div>}{work === 'extract' && <div className="ocr-live-state"><span className="ocr-live-spinner" /><b>Extracting Khatauni structure from OCR tokens…</b></div>}
    </section>}

    {!isTerminal && <section className="card final-decision"><div className="section-head"><div><h3>Officer decision</h3><p>Compare the source and structured values before recording a decision.</p></div><div className="actions"><Button onClick={() => setPendingDecision('approve')} loading={work === 'approve'} loadingText="Verifying…" disabled={!hasExtraction || Boolean(work)}><CheckCircle size={15} /> Approve & Verify</Button><Button variant="secondary" onClick={() => setPendingDecision('mark-review')} loading={work === 'mark-review'} loadingText="Updating…" disabled={Boolean(work)}><AlertTriangle size={15} /> Needs Review</Button><Button variant="danger" onClick={() => setRejectOpen(true)} loading={work === 'reject'} disabled={Boolean(work)}><XCircle size={15} /> Reject</Button></div></div></section>}
    {pendingDecision && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="decision-title"><div className="modal-card decision-modal"><div className="eyebrow">OFFICER DECISION</div><h3 id="decision-title">{pendingDecision === 'approve' ? 'Approve and verify this record?' : 'Mark this record for further review?'}</h3><p>{pendingDecision === 'approve' ? 'This creates or updates the verified digital record using the reviewed values.' : 'The record remains in the review queue for a later decision.'}</p><div className="actions"><Button variant="secondary" onClick={() => setPendingDecision('')}>Cancel</Button><Button onClick={() => { const action = pendingDecision; setPendingDecision(''); decide(action); }} loading={work === pendingDecision} loadingText={pendingDecision === 'approve' ? 'Verifying…' : 'Updating…'}>{pendingDecision === 'approve' ? 'Approve & Verify' : 'Mark Needs Review'}</Button></div></div></div>}
    {rejectOpen && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="reject-title"><div className="modal-card"><h3 id="reject-title">Reject record</h3><p>Choose a meaningful reason before confirming. This is saved in the audit trail and shown to the submitting citizen.</p><div className="field"><label>Reason Category</label><select value={reasonCategory} onChange={event => setReasonCategory(event.target.value)} disabled={Boolean(work)}><option value="">Select a reason</option>{['Poor Scan Quality', 'Incomplete Document', 'Incorrect Document', 'Unreadable Information', 'Duplicate Submission', 'Information Mismatch', 'Other'].map(reason => <option key={reason}>{reason}</option>)}</select></div><div className="field"><label>Officer Note {reasonCategory === 'Other' ? '(required)' : '(optional)'}</label><textarea value={officerNote} onChange={event => setOfficerNote(event.target.value)} placeholder="Explain what the citizen needs to correct." disabled={Boolean(work)}/></div><div className="actions" style={{marginTop: 16}}><Button variant="secondary" onClick={() => setRejectOpen(false)} disabled={Boolean(work)}>Cancel</Button><Button variant="danger" loading={work === 'reject'} loadingText="Rejecting…" disabled={!reasonCategory || (reasonCategory === 'Other' && !officerNote.trim()) || Boolean(work)} onClick={() => decide('reject', {reason_category: reasonCategory, officer_note: officerNote.trim() || null})}>Confirm rejection</Button></div></div></div>}
    {pendingDeleteRow && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="delete-row-title"><div className="modal-card decision-modal"><div className="eyebrow">TABLE CORRECTION</div><h3 id="delete-row-title">Remove row {pendingDeleteRow.row_index + 1}?</h3><p>This removes the row from the digital record and records the action in the audit trail.</p><div className="actions"><Button variant="secondary" onClick={() => setPendingDeleteRow(null)}>Cancel</Button><Button variant="danger" onClick={() => { const row = pendingDeleteRow; setPendingDeleteRow(null); mutate('delete-row', () => api.deleteDynamicTableRow(id, digitization.table.id, row.row_index), 'Khatauni row removed and audited.'); }} loading={work === 'delete-row'} loadingText="Removing…">Remove row</Button></div></div></div>}
  </>;
}
