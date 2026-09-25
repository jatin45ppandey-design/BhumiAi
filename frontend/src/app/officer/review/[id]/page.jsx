'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AlertTriangle, CheckCircle, FileText, Minus, Plus, Save, ScanLine, Search, Trash2, XCircle, ZoomIn } from 'lucide-react';
import { api } from '../../../../lib/api';
import { bilingualKhatauniLabel } from '../../../../lib/khatauniLabels';
import { supportsHindiPhoneticInput } from '../../../../lib/hindiTransliteration';
import { Button, ErrorMessage, Loader, StatusBadge, Toast } from '../../../../components/common/UI';
import ConfidenceBadge, { ValidationBadge } from '../../../../components/officer/ConfidenceBadge';
import AuthenticatedDocument from '../../../../components/documents/AuthenticatedDocument';
import HindiPhoneticInput from '../../../../components/officer/HindiPhoneticInput';

const valueOf = (entry) => entry?.officer_value ?? entry?.final_value ?? entry?.ai_value ?? entry?.raw_ocr_value ?? '';
const ocrValueOf = (entry) => entry?.raw_ocr_value ?? entry?.ai_value ?? '';
const validationOf = (entry) => entry?.validation ?? entry?.audit_metadata?.validation;
const hasDraft = (drafts, key) => Object.prototype.hasOwnProperty.call(drafts, key);
const safeErrorMessage = (error) => {
  const message = String(error?.message || '');
  return /(?:\bat\s+\w+\s*\(|traceback|[A-Za-z]:\\|\/[^\s]+\.(?:py|js))/i.test(message)
    ? 'We could not complete that request. Check the record and try again.'
    : message || 'We could not complete that request. Please try again.';
};
const FIELD_GROUPS = [
  ['Location Details', /district|tehsil|village|pargana|state|location/i],
  ['Record Details', /khata|gata|khasra|plot|area|share|land|revenue|year|number|serial/i],
  ['Holder Details', /holder|khatedar|guardian|father|husband|owner|name/i],
];
function groupedFields(items) {
  const groups = FIELD_GROUPS.map(([title]) => [title, []]);
  const other = [];
  items.forEach((field) => {
    const label = String(field.original_label || field.normalized_label || '');
    const index = FIELD_GROUPS.findIndex(([, pattern]) => pattern.test(label));
    (index === -1 ? other : groups[index][1]).push(field);
  });
  return [...groups.filter(([, fields]) => fields.length), ...(other.length ? [['Other Details', other]] : [])];
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

function SourceDocument({ document, processedPath, sourceMode, setSourceMode, zoom, setZoom, fit, setFit, processingActions }) {
  const selectedPath = sourceMode === 'enhanced' && processedPath ? processedPath : document?.file_path;
  const isPdf = selectedPath?.toLowerCase().endsWith('.pdf');
  const variant = sourceMode === 'enhanced' && processedPath ? 'processed' : 'original';
  return <section className="card evidence-pane">
    <div className="section-head evidence-head">
      <div><div className="eyebrow">SOURCE DOCUMENT</div><h3>Source Document</h3><p>Compare the original record with its structured digital version.</p></div>
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
    {processingActions}
  </section>;
}

function ExactDuplicateReview({match, onContinue, onReject}) {
  if (!match?.duplicate) return null;
  const verified = Boolean(match.verified_record_id);
  return <section className="card duplicate-review-card">
    <div className="duplicate-brief"><div><div className="eyebrow">⚠ EXACT DOCUMENT MATCH DETECTED</div><b>Existing Submission {match.matched_submission_id ? `#${match.matched_submission_id}` : 'unavailable'}</b><span>Status: {match.matched_status || 'Unavailable'}</span></div><div className="actions">{verified && <Button variant="secondary" onClick={() => window.location.assign(`/officer/records/${match.verified_record_id}`)}>View Existing Record</Button>}<Button variant="secondary" onClick={onContinue}>Continue Review</Button>{verified && <Button variant="danger" onClick={onReject}>Reject as Duplicate</Button>}</div></div>
    <details className="duplicate-details"><summary>View details</summary><div className="review-meta"><div><span>VERIFIED RECORD</span>{match.verified_record_code ? `${match.verified_record_code} (#${match.verified_record_id})` : 'No verified record'}</div><div><span>VERIFIED AT</span>{match.verified_at ? new Date(match.verified_at).toLocaleString() : 'Not verified'}</div></div></details>
  </section>;
}

function ValidationSummaryCard({ruleValidation, crossValidation, structuredDuplicate, loading}) {
  if (!loading && !ruleValidation && !crossValidation && !structuredDuplicate) return null;
  const reviewRequired = ruleValidation?.status === 'REVIEW_REQUIRED' || crossValidation?.status === 'REVIEW_REQUIRED' || structuredDuplicate?.status === 'POSSIBLE_DUPLICATE';
  if (loading && !ruleValidation && !crossValidation && !structuredDuplicate) return <section className="card validation-summary"><div className="eyebrow">VALIDATION SUMMARY</div><small>Checking reviewed values against deterministic advisory rules and verified BhumiAI records…</small></section>;
  const ruleReview = ruleValidation?.summary?.review || 0;
  const differences = crossValidation?.summary?.differences || 0;
  const duplicateCount = structuredDuplicate?.summary?.possible_duplicates || 0;
  return <section className={`card validation-summary ${reviewRequired ? 'review-required' : 'consistent'}`}>
    <div className="validation-summary-head"><div><div className="eyebrow">VALIDATION SUMMARY</div><h3>{reviewRequired ? 'REVIEW REQUIRED' : 'NO REVIEW FLAGS'}</h3><p>Advisory signals only — the officer retains the final decision.</p></div>{loading && <small>Refreshing…</small>}</div>
    <div className="validation-signals">
      <details><summary><span>Rule-based validation</span><b>{ruleValidation?.status?.replaceAll('_', ' ') || 'UNAVAILABLE'}</b><small>{ruleValidation ? `${ruleValidation.summary?.passed || 0} passed · ${ruleReview} requires review` : 'Not available'}</small></summary>{ruleValidation?.rules?.filter((rule) => rule.status === 'REVIEW').map((rule, index) => <div className="validation-evidence" key={`${rule.rule_id}-${index}`}><b>{rule.rule_id} · {rule.name.replaceAll('_', ' ')}</b><span>{rule.message}</span>{rule.plot_number && <span>Plot {rule.plot_number}</span>}</div>)}</details>
      <details><summary><span>Cross-record validation</span><b>{crossValidation?.status?.replaceAll('_', ' ') || 'UNAVAILABLE'}</b><small>{crossValidation ? `${crossValidation.candidate_count || 0} references · ${differences} differences` : 'Not available'}</small></summary>{crossValidation?.references?.map((reference) => <div className="validation-evidence" key={reference.record_db_id}><b>Compared with {reference.record_id}</b><span>Matched on: {reference.matched_on.join(', ')} · Differences: {reference.difference_count}</span>{reference.differences.map((difference, index) => <span key={`${difference.field}-${index}`}>{difference.field.replaceAll('_', ' ')}: {difference.current_value} → {difference.reference_value}</span>)}</div>)}</details>
      <details><summary><span>Structured duplicate check</span><b>{structuredDuplicate?.status?.replaceAll('_', ' ') || 'UNAVAILABLE'}</b><small>{structuredDuplicate ? `${duplicateCount} possible duplicate${duplicateCount === 1 ? '' : 's'}` : 'Not available'}</small></summary>{structuredDuplicate?.matches?.map((match) => <div className="validation-evidence" key={match.record_db_id}><b>Possible match: {match.record_id}</b><span>Matched on {match.matched_identity.join(', ')} · Plots: {match.matched_plots.join(', ')}</span><span>Matching fields: {match.matching_fields.join(', ')}</span></div>)}</details>
    </div>
  </section>;
}

function DigitalKhatauni({ digitization, digitizationLoading, work, isTerminal, typingMode, setTypingMode, drafts, isDirty, error, onFieldChange, onCellChange, onAddRow, onDeleteRow, onSave, onNeedsReview, onVerify, onReject }) {
  const { items, table } = digitization;
  const fieldGroups = groupedFields(items);
  if (digitizationLoading) return <section className="card khatauni-pane khatauni-loading" aria-label="Loading structured record"><div className="section-head"><div><div className="eyebrow">DIGITAL KHATAUNI</div><h3>Loading structured record…</h3><p>The source record remains available while extracted fields load.</p></div></div><div className="khatauni-fields"><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/></div><div className="skeleton-block skeleton-khatauni-table"/></section>;
  return <section className="card khatauni-pane structured-pane">
    <div className="section-head"><div><div className="eyebrow">STRUCTURED / EXTRACTED RECORD</div><h3>Structured Record</h3><p>Review and correct the extracted record beside the source document.</p></div>{!isTerminal && <div className="typing-mode" role="group" aria-label="Correction typing mode"><span>Typing</span><button type="button" className={typingMode === 'en' ? 'active' : ''} aria-pressed={typingMode === 'en'} onClick={() => setTypingMode('en')}>EN</button><button type="button" className={typingMode === 'hi' ? 'active' : ''} aria-pressed={typingMode === 'hi'} onClick={() => setTypingMode('hi')}>हिंदी</button></div>}</div>
    <div className="khatauni-fields" onChangeCapture={(event) => {
      const fieldId = event.target.closest('[data-field-id]')?.dataset.fieldId;
      const field = items.find((item) => String(item.id) === fieldId);
      if (field) onFieldChange(field, event.target.value);
    }}>
      {items.length ? fieldGroups.map(([title, fields]) => <section className="field-group" key={title}><h4>{title}</h4>{fields.map((field) => <label className="khatauni-field" data-field-id={field.id} key={field.id}>
        <span>{bilingualKhatauniLabel(field.original_label)}</span>
        {supportsHindiPhoneticInput(bilingualKhatauniLabel(field.original_label)) ? <HindiPhoneticInput key={`${field.id}-${valueOf(field)}`} defaultValue={valueOf(field)} hindiMode={typingMode === 'hi'} placeholder="स्वचालित रूप से पता नहीं चला / Not automatically detected" onValueChange={value => onFieldChange(field, value)} onCommit={value => value !== String(valueOf(field)) && onFieldChange(field, value)} disabled={Boolean(work)} /> : <input key={`${field.id}-${valueOf(field)}`} defaultValue={valueOf(field)} placeholder="स्वचालित रूप से पता नहीं चला / Not automatically detected" onBlur={(event) => event.target.value !== String(valueOf(field)) && onFieldChange(field, event.target.value)} disabled={Boolean(work)} />}
        <small className="recognition-indicators"><span className="indicator-label">Recognition evidence</span><ConfidenceBadge value={field.ai_confidence} /><ValidationBadge validation={validationOf(field)} /></small>
        {hasDraft(drafts, `field-${field.id}`) && <em title={`Original OCR: ${ocrValueOf(field) || 'Blank'}`}><span className="edited-tag">Edited</span> Unsaved correction</em>}
        {field.officer_value !== null && field.officer_value !== undefined && <em><span className="edited-tag">Edited</span> OCR: {ocrValueOf(field) || 'रिक्त / Blank'}</em>}
      </label>)}</section>) : <div className="khatauni-empty">Extract Khatauni Data to create the empty schema and populate OCR matches.</div>}
    </div>
    <div className="khatauni-table-head"><div><b>Land Parcel Details</b><small>Rows originate from OCR; manual rows are explicitly marked.</small></div><Button variant="secondary" onClick={onAddRow} disabled={!table?.id || Boolean(work)}><Plus size={14} /> Add Row</Button></div>
    {table ? <div className="table-wrap khatauni-table-wrap"><table className="data-table khatauni-table">
      <thead><tr>{table.headers.map((header) => <th key={header.column_index}>{bilingualKhatauniLabel(header.label)}</th>)}<th>स्थिति / Status</th></tr></thead>
      <tbody onChangeCapture={(event) => {
        const rowIndex = Number(event.target.closest('tr')?.dataset.rowIndex);
        const columnIndex = event.target.closest('td')?.cellIndex;
        const cell = table.rows.find((row) => row.row_index === rowIndex)?.cells.find((candidate) => candidate.column_index === columnIndex);
        if (cell) onCellChange(cell, event.target.value);
      }}>{table.rows.length ? table.rows.map((row) => {
        const manual = row.cells.length > 0 && row.cells.every((cell) => cell.confidence_source === 'officer_manual');
        return <tr key={row.row_index} data-row-index={row.row_index}>{table.headers.map((header) => {
          const cell = row.cells.find((candidate) => candidate.column_index === header.column_index);
          const supportsHindi = supportsHindiPhoneticInput(bilingualKhatauniLabel(header.label));
          return <td key={header.column_index} className={cell && hasDraft(drafts, `cell-${cell.id}`) ? 'has-unsaved-correction' : ''}>{cell ? <div className="khatauni-cell">{supportsHindi ? <HindiPhoneticInput key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} hindiMode={typingMode === 'hi'} placeholder="मान दर्ज करें / Enter Value" onValueChange={value => onCellChange(cell, value)} onCommit={value => value !== String(valueOf(cell)) && onCellChange(cell, value)} disabled={Boolean(work)} /> : <input key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} placeholder="मान दर्ज करें / Enter Value" onBlur={(event) => event.target.value !== String(valueOf(cell)) && onCellChange(cell, event.target.value)} disabled={Boolean(work)} />}<span className="recognition-indicators"><ConfidenceBadge value={cell.ai_confidence} /><ValidationBadge validation={validationOf(cell)} /></span>{cell.officer_value !== null && cell.officer_value !== undefined && <small><span className="edited-tag">Edited</span> OCR: {ocrValueOf(cell) || 'रिक्त / Blank'}</small>}</div> : <span className="empty-cell">रिक्त / Blank</span>}</td>;
        })}<td><span className={`source-tag ${manual ? 'manual' : 'ocr'}`}>{manual ? 'Added by Officer' : 'OCR'}</span><button className="table-delete-button" type="button" onClick={() => onDeleteRow(row)} disabled={Boolean(work)}><Trash2 size={13} /> Delete row</button></td></tr>;
      }) : <tr><td colSpan={table.headers.length + 1} className="dynamic-empty-row">कोई पंक्ति विश्वसनीय रूप से नहीं मिली। सही पंक्ति अधिकारी जोड़ सकते हैं। / No row was detected reliably. An officer can add the correct row.</td></tr>}</tbody>
    </table></div> : <div className="khatauni-empty">No Khatauni table has been extracted yet.</div>}
    {!isTerminal && <footer className="review-action-footer" aria-label="Review actions"><div><span className="eyebrow">OFFICER CORRECTION</span><small>{isDirty ? 'Unsaved changes — save edits before recording a final decision.' : 'Save edits before recording a final decision.'}</small>{error && <p className="review-action-error" role="alert">{error}</p>}</div><div className="actions"><Button variant="secondary" onClick={onSave} loading={work === 'save-corrections'} loadingText="Saving…" disabled={!isDirty || Boolean(work)}><Save size={15} /> Save Corrections</Button><Button variant="secondary" onClick={onNeedsReview} disabled={isDirty || Boolean(work)}><AlertTriangle size={15} /> Needs Review</Button><Button onClick={onVerify} disabled={!items.length || !table || isDirty || Boolean(work)}><CheckCircle size={15} /> Verify Record</Button><Button variant="danger" onClick={onReject} disabled={isDirty || Boolean(work)}><XCircle size={15} /> Reject</Button></div></footer>}
  </section>;
}

function LandParcelReview({digitization, work, isTerminal, typingMode, drafts, onCellChange, onAddRow, onDeleteRow}) {
  const {table} = digitization;
  if (!table) return <section className="card land-table-pane"><div className="section-head"><div><div className="eyebrow">LAND RECORD REVIEW</div><h3>Khatauni / Land Parcel Table</h3></div></div><div className="khatauni-empty">No Khatauni table has been extracted yet.</div></section>;
  return <section className="card land-table-pane">
    <div className="section-head land-table-head"><div><div className="eyebrow">LAND RECORD REVIEW</div><h3>Khatauni / Land Parcel Table</h3><p>Review parcel details, then record the officer decision alongside this table.</p></div>{!isTerminal && <Button variant="secondary" onClick={onAddRow} disabled={!table.id || Boolean(work)}><Plus size={14} /> Add Row</Button>}</div>
    <div className="table-wrap khatauni-table-wrap"><table className="data-table khatauni-table">
      <thead><tr>{table.headers.map((header) => <th key={header.column_index}>{bilingualKhatauniLabel(header.label)}</th>)}<th>Status</th></tr></thead>
      <tbody onChangeCapture={(event) => {
        const rowIndex = Number(event.target.closest('tr')?.dataset.rowIndex);
        const columnIndex = event.target.closest('td')?.cellIndex;
        const cell = table.rows.find((row) => row.row_index === rowIndex)?.cells.find((candidate) => candidate.column_index === columnIndex);
        if (cell) onCellChange(cell, event.target.value);
      }}>{table.rows.length ? table.rows.map((row) => {
        const manual = row.cells.length > 0 && row.cells.every((cell) => cell.confidence_source === 'officer_manual');
        return <tr key={row.row_index} data-row-index={row.row_index}>{table.headers.map((header) => {
          const cell = row.cells.find((candidate) => candidate.column_index === header.column_index);
          const supportsHindi = supportsHindiPhoneticInput(bilingualKhatauniLabel(header.label));
          return <td key={header.column_index} className={cell && hasDraft(drafts, `cell-${cell.id}`) ? 'has-unsaved-correction' : ''}>{cell ? <div className="khatauni-cell">{supportsHindi ? <HindiPhoneticInput key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} hindiMode={typingMode === 'hi'} placeholder="मान दर्ज करें / Enter value" onValueChange={(value) => onCellChange(cell, value)} onCommit={(value) => value !== String(valueOf(cell)) && onCellChange(cell, value)} disabled={Boolean(work)} /> : <input key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} placeholder="Enter value" onBlur={(event) => event.target.value !== String(valueOf(cell)) && onCellChange(cell, event.target.value)} disabled={Boolean(work)} />}<span className="recognition-indicators"><ConfidenceBadge value={cell.ai_confidence} /><ValidationBadge validation={validationOf(cell)} /></span>{cell.officer_value !== null && cell.officer_value !== undefined && <small title={`Original OCR: ${ocrValueOf(cell) || 'Blank'}`}><span className="edited-tag">Edited</span> OCR value available</small>}</div> : <span className="empty-cell">Blank</span>}</td>;
        })}<td><span className={`source-tag ${manual ? 'manual' : 'ocr'}`}>{manual ? 'Added by Officer' : 'OCR'}</span>{!isTerminal && <button className="table-delete-button" type="button" onClick={() => onDeleteRow(row)} disabled={Boolean(work)}><Trash2 size={13} /> Delete row</button>}</td></tr>;
      }) : <tr><td colSpan={table.headers.length + 1} className="dynamic-empty-row">No row was detected reliably. An officer can add the correct row.</td></tr>}</tbody>
    </table></div>
  </section>;
}

function OfficerDecisionPanel({digitization, drafts, isDirty, error, work, isTerminal, onSave, onNeedsReview, onVerify, onReject}) {
  if (isTerminal) return null;
  const entries = [...digitization.items, ...(digitization.table?.cells || [])];
  const edited = new Set([...Object.keys(drafts), ...entries.filter((entry) => entry.officer_value !== null && entry.officer_value !== undefined).map((entry) => `${entry.table_id ? 'cell' : 'field'}-${entry.id}`)]).size;
  const lowConfidence = entries.filter((entry) => entry.ai_confidence !== null && entry.ai_confidence !== undefined && entry.ai_confidence < 65).length;
  const needsReview = entries.filter((entry) => ['NEEDS_REVIEW', 'UNRESOLVED'].includes(validationOf(entry)?.status)).length;
  return <aside className="card officer-decision-panel" aria-label="Officer decision">
    <div className="officer-decision-head"><div className="eyebrow">OFFICER REVIEW</div><h3>Decision</h3></div>
    <dl className="decision-summary"><div><dt>Edited fields</dt><dd>{edited}</dd></div><div><dt>Low confidence</dt><dd>{lowConfidence}</dd></div><div><dt>Needs review</dt><dd>{needsReview}</dd></div></dl>
    <div className={`decision-dirty ${isDirty ? 'is-dirty' : ''}`}>{isDirty ? 'Unsaved changes' : 'All corrections saved'}</div>
    {error && <p className="review-action-error" role="alert">{error}</p>}
    <div className="decision-actions"><Button variant="secondary" onClick={onSave} loading={work === 'save-corrections'} loadingText="Saving…" disabled={!isDirty || Boolean(work)}><Save size={15} /> Save Corrections</Button><Button variant="secondary" onClick={onNeedsReview} disabled={isDirty || Boolean(work)}><AlertTriangle size={15} /> Needs Review</Button><hr/><Button onClick={onVerify} disabled={!digitization.items.length || !digitization.table || isDirty || Boolean(work)}><CheckCircle size={15} /> Verify Record</Button><Button variant="danger" onClick={onReject} disabled={isDirty || Boolean(work)}><XCircle size={15} /> Reject</Button></div>
  </aside>;
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
  const [typingMode, setTypingMode] = useState('en');
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState(true);
  const [work, setWork] = useState('');
  const [drafts, setDrafts] = useState({});
  const [structuralDirty, setStructuralDirty] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [rejectOpen, setRejectOpen] = useState(false);
  const [pendingDecision, setPendingDecision] = useState('');
  const [pendingDeleteRow, setPendingDeleteRow] = useState(null);
  const [reasonCategory, setReasonCategory] = useState('');
  const [officerNote, setOfficerNote] = useState('');
  const [duplicate, setDuplicate] = useState(null);
  const [ruleValidation, setRuleValidation] = useState(null);
  const [crossValidation, setCrossValidation] = useState(null);
  const [structuredDuplicate, setStructuredDuplicate] = useState(null);
  const [validationLoading, setValidationLoading] = useState(false);
  const hasRawOcr = Boolean(ocr?.raw_text?.trim());
  const hasExtraction = digitization.items.length > 0 && Boolean(digitization.table);
  const isDirty = structuralDirty || Object.keys(drafts).length > 0;

  useEffect(() => {
    if (!isDirty) return undefined;
    const warnBeforeUnload = (event) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [isDirty]);

  async function refreshDigitization() { setDigitization(normalizeDigitization(await api.digitization(id))); }
  async function refreshValidationSignals() {
    setValidationLoading(true);
    try {
      const [rules, crossRecord, structured] = await Promise.all([
        api.ruleValidation(id).catch(() => null),
        api.crossRecordValidation(id).catch(() => null),
        api.structuredDuplicateCheck(id).catch(() => null),
      ]);
      setRuleValidation(rules); setCrossValidation(crossRecord); setStructuredDuplicate(structured);
    } finally { setValidationLoading(false); }
  }

  useEffect(() => {
    let active = true;
    api.submissions({documentId: id}).then(async (submissions) => {
      if (!active) return;
      const found = submissions[0];
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
      if (active && structure) {
        setDigitization(normalizeDigitization(structure));
        if (structure.items?.length || structure.tables?.length) refreshValidationSignals();
      }
    }).catch(() => {}).finally(() => active && setDigitizationLoading(false));
    return () => { active = false; };
  }, [id]);

  async function execute(kind) {
    if (work) return;
    setWork(kind); setError(''); setNotice('');
    try {
      if (kind === 'preprocess') {
        const result = await api.preprocess(id); setProcessedPath(result.processed_file_path); setSourceMode('enhanced'); setOcr(null); setDigitization({ items: [], table: null, summary: {} }); setRuleValidation(null); setCrossValidation(null); setStructuredDuplicate(null); setNotice('OpenCV preprocessing completed. Enhanced evidence is ready.');
      } else if (kind === 'ocr') {
        const result = await api.ocr(id, processedPath); setOcr(result); setDigitization({ items: [], table: null, summary: {} }); setRuleValidation(null); setCrossValidation(null); setStructuredDuplicate(null);
        if (result.status !== 'COMPLETED') throw new Error(result.message || 'Document recognition could not process this record.');
        setNotice('Document recognition completed. Technical evidence is available below.');
      } else if (kind === 'extract') {
        const result = await api.extract(id, ocr?.ocr_id); setDigitization(normalizeDigitization(result)); await refreshValidationSignals(); setNotice(result.message || 'Khatauni extraction completed.');
      }
    } catch (actionError) { setError(safeErrorMessage(actionError)); } finally { setWork(''); }
  }

  async function mutate(key, action, message, marksDirty = true) {
    if (work) return;
    setWork(key); setError('');
    try { await action(); await refreshDigitization(); await refreshValidationSignals(); if (marksDirty) setStructuralDirty(true); setNotice(message); } catch (mutationError) { setError(safeErrorMessage(mutationError)); } finally { setWork(''); }
  }

  function stageChange(kind, entry, value) {
    const key = `${kind}-${entry.id}`;
    const original = String(valueOf(entry));
    setDrafts((current) => {
      if (String(value) === original) {
        const {[key]: _removed, ...rest} = current;
        return rest;
      }
      return {...current, [key]: value};
    });
  }

  const updateField = (field, value) => stageChange('field', field, value);
  const updateCell = (cell, value) => stageChange('cell', cell, value);
  const addRow = () => mutate('add-row', () => api.createDynamicTableRow(id, digitization.table.id, {}), 'Manual Khatauni row added and audited.', true);
  const deleteRow = row => setPendingDeleteRow(row);
  async function saveCorrections() {
    if (work || !isDirty) return;
    setWork('save-corrections'); setError('');
    try {
      await Promise.all(Object.entries(drafts).map(([key, value]) => {
        const [kind, entityId] = key.split('-');
        return kind === 'field'
          ? api.updateDynamicField(id, entityId, {officer_value: value})
          : api.updateDynamicTableCell(id, digitization.table.id, entityId, {officer_value: value});
      }));
      await refreshDigitization();
      await refreshValidationSignals();
      setDrafts({}); setStructuralDirty(false);
      setNotice('Corrections saved; original OCR remains preserved.');
    } catch (saveError) { setError(safeErrorMessage(saveError)); } finally { setWork(''); }
  }

  async function decide(action, rejection) {
    if (work) return;
    setWork(action); setError('');
    try { await api.decision(id, action, rejection); router.push(action === 'approve' ? '/officer/records' : '/officer/submissions'); } catch (decisionError) { setError(safeErrorMessage(decisionError)); } finally { setWork(''); }
  }

  async function continueDuplicateReview() {
    if (!duplicate?.matched_document_id || work) return;
    setWork('duplicate-continue'); setError('');
    try {
      await api.duplicateContinue(id, duplicate.matched_document_id);
      setDuplicate(null);
      setNotice('Duplicate review recorded. The submission remains active.');
    } catch (duplicateError) { setError(safeErrorMessage(duplicateError)); }
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
  const steps = [['Upload', Boolean(sourceDocument?.file_path)], ['Enhance', Boolean(processedPath)], ['Recognize', Boolean(ocr)], ['Extract', hasExtraction], ['Review', false], ['Verified', isVerified]];
  const currentStep = isVerified ? 5 : 4;
  const processingActions = !isTerminal && <div className="document-processing"><div><span className="eyebrow">DOCUMENT PROCESSING</span><small>Prepare the source before reviewing the extracted record.</small></div><div className="actions"><Button variant="secondary" onClick={() => execute('preprocess')} loading={work === 'preprocess'} disabled={Boolean(work)}><ScanLine size={15} /> Preprocess</Button><Button onClick={() => execute('ocr')} loading={work === 'ocr'} disabled={!processedPath || Boolean(work)}><Search size={15} /> Run OCR</Button><Button variant="secondary" onClick={() => execute('extract')} loading={work === 'extract'} disabled={!hasRawOcr || Boolean(work)}>Extract Data</Button></div>{work === 'ocr' && <div className="ocr-live-state"><span className="ocr-live-spinner" /><b>Running OCR on the actual document with Tesseract hin+eng...</b></div>}{work === 'extract' && <div className="ocr-live-state"><span className="ocr-live-spinner" /><b>Extracting Khatauni structure from OCR tokens...</b></div>}</div>;

  return <>
    <div className="page-title review-page-title"><div><div className="eyebrow">OFFICER WORKSPACE</div><h2>Record Review</h2><p>Submission #{submission.id || sourceDocument.id} · {sourceDocument.original_filename} · Uploaded {new Date(sourceDocument.uploaded_at || submission.submitted_at).toLocaleString()}</p><p>Submitted by {submission.user?.name} ({submission.user?.email})</p></div><StatusBadge status={submission.status} /></div>
    <ErrorMessage>{error}</ErrorMessage><Toast message={notice} onDismiss={() => setNotice('')}/>{work.startsWith('field-') || work.startsWith('cell-') ? <div className="notice" role="status">Saving correction…</div> : null}{isRejected && <div className="notice warn"><b>Rejected record — read-only.</b><br/>Reason: {submission.rejection?.reason_category || 'Unavailable'}{submission.rejection?.officer_note && <><br/>{submission.rejection.officer_note}</>}</div>}{isVerified && <div className="notice"><b>Verified record — read-only.</b><br/>Open the permanent verified record to review or export it.</div>}
    <section className="card khatauni-stepper" aria-label="Document processing progress"><ol>{steps.map(([label, done], index) => <li className={done ? 'complete' : (index === currentStep ? 'current' : '')} key={label}><span aria-hidden="true">{done ? '✓' : index === currentStep ? '●' : '○'}</span><b>{label}</b></li>)}</ol></section>
    {!isTerminal && <ExactDuplicateReview match={duplicate} onContinue={continueDuplicateReview} onReject={rejectAsDuplicate}/>}
    <ValidationSummaryCard ruleValidation={ruleValidation} crossValidation={crossValidation} structuredDuplicate={structuredDuplicate} loading={validationLoading}/>
    <div className="review-workbench"><SourceDocument document={sourceDocument} processedPath={processedPath} sourceMode={sourceMode} setSourceMode={setSourceMode} zoom={zoom} setZoom={setZoom} fit={fit} setFit={setFit} processingActions={processingActions} /><DigitalKhatauni digitization={digitization} digitizationLoading={isTerminal ? false : digitizationLoading} work={isTerminal ? 'read-only' : work} isTerminal={isTerminal} typingMode={typingMode} setTypingMode={setTypingMode} drafts={drafts} isDirty={isDirty} error={error} onFieldChange={updateField} onCellChange={updateCell} onAddRow={addRow} onDeleteRow={deleteRow} onSave={saveCorrections} onNeedsReview={() => isDirty ? setError('Save unsaved corrections before updating this review.') : setPendingDecision('mark-review')} onVerify={() => isDirty ? setError('Save unsaved corrections before verifying this record.') : setPendingDecision('approve')} onReject={() => isDirty ? setError('Save unsaved corrections before rejecting this record.') : setRejectOpen(true)} /></div>
    <section className={`land-review-layout ${isTerminal ? 'terminal-land-review' : ''}`}><LandParcelReview digitization={digitization} work={isTerminal ? 'read-only' : work} isTerminal={isTerminal} typingMode={typingMode} drafts={drafts} onCellChange={updateCell} onAddRow={addRow} onDeleteRow={deleteRow}/><OfficerDecisionPanel digitization={digitization} drafts={drafts} isDirty={isDirty} error={error} work={work} isTerminal={isTerminal} onSave={saveCorrections} onNeedsReview={() => isDirty ? setError('Save unsaved corrections before updating this review.') : setPendingDecision('mark-review')} onVerify={() => isDirty ? setError('Save unsaved corrections before verifying this record.') : setPendingDecision('approve')} onReject={() => isDirty ? setError('Save unsaved corrections before rejecting this record.') : setRejectOpen(true)}/></section>

    {pendingDecision && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="decision-title"><div className="modal-card decision-modal"><div className="eyebrow">OFFICER DECISION</div><h3 id="decision-title">{pendingDecision === 'approve' ? 'Verify this record?' : 'Mark this record for further review?'}</h3><p><b>Submission #{submission.id || sourceDocument.id}</b></p><p>{pendingDecision === 'approve' ? 'Final decision: verification creates or updates the verified digital record using the reviewed values.' : 'The record remains in the review queue for a later decision.'}</p>{error && <p className="review-action-error" role="alert">{error}</p>}<div className="actions"><Button variant="secondary" onClick={() => setPendingDecision('')} disabled={Boolean(work)}>Cancel</Button><Button onClick={() => decide(pendingDecision)} loading={work === pendingDecision} loadingText={pendingDecision === 'approve' ? 'Verifying…' : 'Updating…'} disabled={Boolean(work)}>{pendingDecision === 'approve' ? 'Verify Record' : 'Mark Needs Review'}</Button></div></div></div>}
    {rejectOpen && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="reject-title"><div className="modal-card decision-modal"><div className="eyebrow">OFFICER DECISION</div><h3 id="reject-title">Reject this record?</h3><p><b>Submission #{submission.id || sourceDocument.id}</b></p><p>Final decision: rejection is recorded in the audit trail and shown to the submitting citizen.</p><div className="field"><label>Reason Category</label><select value={reasonCategory} onChange={event => setReasonCategory(event.target.value)} disabled={Boolean(work)}><option value="">Select a reason</option>{['Poor Scan Quality', 'Incomplete Document', 'Incorrect Document', 'Unreadable Information', 'Duplicate Submission', 'Information Mismatch', 'Other'].map(reason => <option key={reason}>{reason}</option>)}</select></div><div className="field"><label>Officer Note {reasonCategory === 'Other' ? '(required)' : '(optional)'}</label><textarea value={officerNote} onChange={event => setOfficerNote(event.target.value)} placeholder="Explain what the citizen needs to correct." disabled={Boolean(work)}/></div>{error && <p className="review-action-error" role="alert">{error}</p>}<div className="actions" style={{marginTop: 16}}><Button variant="secondary" onClick={() => setRejectOpen(false)} disabled={Boolean(work)}>Cancel</Button><Button variant="danger" loading={work === 'reject'} loadingText="Rejecting…" disabled={!reasonCategory || (reasonCategory === 'Other' && !officerNote.trim()) || Boolean(work)} onClick={() => decide('reject', {reason_category: reasonCategory, officer_note: officerNote.trim() || null})}>Confirm rejection</Button></div></div></div>}
    {pendingDeleteRow && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="delete-row-title"><div className="modal-card decision-modal"><div className="eyebrow">TABLE CORRECTION</div><h3 id="delete-row-title">Remove row {pendingDeleteRow.row_index + 1}?</h3><p>This removes the row from the digital record and records the action in the audit trail.</p><div className="actions"><Button variant="secondary" onClick={() => setPendingDeleteRow(null)}>Cancel</Button><Button variant="danger" onClick={() => { const row = pendingDeleteRow; setPendingDeleteRow(null); mutate('delete-row', () => api.deleteDynamicTableRow(id, digitization.table.id, row.row_index), 'Khatauni row removed and audited.'); }} loading={work === 'delete-row'} loadingText="Removing…">Remove row</Button></div></div></div>}
  </>;
}
