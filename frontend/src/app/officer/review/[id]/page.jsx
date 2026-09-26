'use client';

import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AlertTriangle, CheckCircle, ChevronLeft, ChevronRight, FileText, LocateFixed, Minus, Plus, Save, ScanLine, Search, Trash2, XCircle, ZoomIn } from 'lucide-react';
import { api } from '../../../../lib/api';
import { bilingualKhatauniLabel } from '../../../../lib/khatauniLabels';
import { supportsHindiPhoneticInput } from '../../../../lib/hindiTransliteration';
import { Button, ErrorMessage, Loader, StatusBadge, Toast } from '../../../../components/common/UI';
import ConfidenceBadge from '../../../../components/officer/ConfidenceBadge';
import AuthenticatedDocument from '../../../../components/documents/AuthenticatedDocument';
import HindiPhoneticInput from '../../../../components/officer/HindiPhoneticInput';

const valueOf = (entry) => entry?.officer_value ?? entry?.final_value ?? entry?.ai_value ?? entry?.raw_ocr_value ?? '';
const ocrValueOf = (entry) => entry?.raw_ocr_value ?? entry?.ai_value ?? '';
const validationOf = (entry) => entry?.validation ?? entry?.audit_metadata?.validation;
const hasDraft = (drafts, key) => Object.prototype.hasOwnProperty.call(drafts, key);
const LOW_CONFIDENCE_THRESHOLD = 65;
const CORE_FIELD_ORDER = ['district', 'tehsil', 'revenue_village', 'village_name', 'village_code', 'pargana', 'crop_year', 'khata_number'];
const CORE_FIELD_KEYS = new Set(CORE_FIELD_ORDER);
const HIDDEN_REVIEW_FIELD_KEYS = new Set(['lekhpal_name']);
const PRIMARY_PARCEL_KEYS = new Set(['plot_number', 'holder_name', 'guardian_name', 'share', 'area']);
const safeErrorMessage = (error) => {
  const message = String(error?.message || '');
  return /(?:\bat\s+\w+\s*\(|traceback|[A-Za-z]:\\|\/[^\s]+\.(?:py|js))/i.test(message)
    ? 'We could not complete that request. Check the record and try again.'
    : message || 'We could not complete that request. Please try again.';
};
const confidenceText = (value) => value === null || value === undefined
  ? 'Unavailable'
  : `${Math.round(value)}% · ${value < LOW_CONFIDENCE_THRESHOLD ? 'Low' : value < 85 ? 'Medium' : 'High'}`;
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
function visibleReviewField(field) {
  return !HIDDEN_REVIEW_FIELD_KEYS.has(schemaKeyOf(field));
}
function parcelColumns(table) {
  const columns = table.headers.map((header) => ({
    ...header,
    schemaKey: schemaKeyOf(table.rows.flatMap(row => row.cells).find(cell => cell.column_index === header.column_index)),
  }));
  const typeColumn = columns.find(column => column.schemaKey === 'land_type') || columns.find(column => column.schemaKey === 'land_category');
  const matched = columns.filter(column => PRIMARY_PARCEL_KEYS.has(column.schemaKey) || column.column_index === typeColumn?.column_index);
  const primary = matched.length ? matched : columns.slice(0, 6);
  return {primary, secondary: columns.filter(column => !primary.some(item => item.column_index === column.column_index))};
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

function SourceDocument({ document, processedPath, sourceMode, setSourceMode, zoom, setZoom, fit, setFit, processingActions, selectedEvidence }) {
  const selectedPath = sourceMode === 'enhanced' && processedPath ? processedPath : document?.file_path;
  const isPdf = selectedPath?.toLowerCase().endsWith('.pdf');
  const variant = sourceMode === 'enhanced' && processedPath ? 'processed' : 'original';
  const canvasRef = useRef(null);
  const [naturalSize, setNaturalSize] = useState({width: 0, height: 0});
  const [canvasSize, setCanvasSize] = useState({width: 0, height: 0});

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const measure = () => setCanvasSize({width: canvas.clientWidth, height: canvas.clientHeight});
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);
  useEffect(() => setNaturalSize({width: 0, height: 0}), [variant]);
  useEffect(() => {
    if (selectedEvidence?.boundingBox && processedPath && sourceMode !== 'enhanced') setSourceMode('enhanced');
  }, [selectedEvidence?.key, selectedEvidence?.boundingBox, processedPath, sourceMode, setSourceMode]);

  const fitScale = naturalSize.width && naturalSize.height && canvasSize.width && canvasSize.height
    ? Math.min(Math.max(1, canvasSize.width - 36) / naturalSize.width, Math.max(1, canvasSize.height - 36) / naturalSize.height)
    : 1;
  const displayScale = fit ? fitScale : zoom;
  const box = clampBoundingBox(selectedEvidence?.boundingBox, naturalSize.width, naturalSize.height);
  const compatibleVariant = !processedPath || sourceMode === 'enhanced';
  const showHighlight = Boolean(box && compatibleVariant && !isPdf);
  const stageStyle = naturalSize.width ? {width: naturalSize.width * displayScale, height: naturalSize.height * displayScale} : undefined;
  const boxStyle = showHighlight ? {left: box.left * displayScale, top: box.top * displayScale, width: Math.max(3, box.width * displayScale), height: Math.max(3, box.height * displayScale)} : undefined;
  const selectedValidation = selectedEvidence?.validation?.status;
  const ruleCheck = selectedValidation === 'PASS' ? 'Pass'
    : selectedValidation === 'NEEDS_REVIEW' ? 'Needs Review'
      : selectedValidation === 'UNRESOLVED' ? 'Unresolved'
        : 'Not available';

  useEffect(() => {
    if (!showHighlight || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const centerX = (box.left + box.width / 2) * displayScale;
    const centerY = (box.top + box.height / 2) * displayScale;
    canvas.scrollTo({left: Math.max(0, centerX - canvas.clientWidth / 2), top: Math.max(0, centerY - canvas.clientHeight / 2), behavior: 'smooth'});
  }, [selectedEvidence?.key, showHighlight, box?.left, box?.top, box?.width, box?.height, displayScale]);

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
    {selectedEvidence && <div className="source-evidence-info" role="status">
      <div className="source-evidence-title"><span className="eyebrow">SELECTED EVIDENCE</span><b>{selectedEvidence.label}</b></div>
      <dl><div><dt>Recognized</dt><dd>{selectedEvidence.recognizedValue || 'Unavailable'}</dd></div><div><dt>Reviewed</dt><dd>{selectedEvidence.value || 'Blank'}</dd></div><div><dt>Recognition Evidence</dt><dd>{confidenceText(selectedEvidence.confidence)}</dd></div><div><dt>Rule Check</dt><dd>{ruleCheck}</dd></div></dl>
      {selectedEvidence.reasons?.length > 0 && <div className="source-evidence-reason"><b>Reason</b><span>{selectedEvidence.reasons.join(' · ')}</span></div>}
      {!selectedEvidence.boundingBox && <em>Source mapping unavailable.</em>}{selectedEvidence.boundingBox && naturalSize.width > 0 && !box && <em>Stored source region is invalid or outside this image.</em>}{selectedEvidence.boundingBox && !compatibleVariant && <em>Open Enhanced view to display this recognition region accurately.</em>}
    </div>}
    <div ref={canvasRef} className={`source-canvas ${fit ? 'fit' : ''}`}>
      {selectedPath ? (isPdf
        ? <AuthenticatedDocument documentId={document.id} variant={variant} isPdf title="Original uploaded PDF" alt="Actual uploaded Khatauni"/>
        : <div className="source-image-stage" style={stageStyle}>
          <AuthenticatedDocument documentId={document.id} variant={variant} alt="Actual uploaded Khatauni" onImageLoad={(event) => setNaturalSize({width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight})}/>
          {showHighlight && <div className="source-evidence-highlight" style={boxStyle} role="img" aria-label={`Highlighted source evidence for ${selectedEvidence.label}`}/>}
        </div>) : <FileText size={46} />}
    </div>
    {processingActions}
  </section>;
}

function comparableValue(value) {
  const digits = {'०':'0','१':'1','२':'2','३':'3','४':'4','५':'5','६':'6','७':'7','८':'8','९':'9'};
  return String(value || '').normalize('NFKC').replace(/[०-९]/g, digit => digits[digit]).replace(/\s+/g, ' ').trim().toLocaleLowerCase();
}
function clampBoundingBox(box, naturalWidth, naturalHeight) {
  if (!box || !naturalWidth || !naturalHeight) return null;
  const left = Number(box.left); const top = Number(box.top);
  const rawRight = box.right !== undefined ? Number(box.right) : left + Number(box.width);
  const rawBottom = box.bottom !== undefined ? Number(box.bottom) : top + Number(box.height);
  if (![left, top, rawRight, rawBottom].every(Number.isFinite)) return null;
  const safeLeft = Math.max(0, Math.min(naturalWidth, left));
  const safeTop = Math.max(0, Math.min(naturalHeight, top));
  const right = Math.max(0, Math.min(naturalWidth, rawRight));
  const bottom = Math.max(0, Math.min(naturalHeight, rawBottom));
  return right > safeLeft && bottom > safeTop ? {left: safeLeft, top: safeTop, width: right - safeLeft, height: bottom - safeTop} : null;
}
function schemaKeyOf(entry) {
  return entry?.audit_metadata?.schema_key || entry?.normalized_label || '';
}
function evidenceEntity(entry, entityType, label, order, plotNumber = '') {
  return {
    key: `${entityType}:${entry.id}`, entityType, entityId: entry.id, schemaKey: schemaKeyOf(entry), label,
    value: valueOf(entry), recognizedValue: ocrValueOf(entry), boundingBox: entry.bounding_box || null,
    sourceTokenIds: entry.source_token_ids || [], confidence: entry.ai_confidence, validation: validationOf(entry),
    rowIndex: entry.row_index, columnIndex: entry.column_index, plotNumber, order,
  };
}
function cellEvidence(cell, row, header, rowOrder = row.row_index) {
  const plotCell = row.cells.find(candidate => schemaKeyOf(candidate) === 'plot_number');
  const plot = valueOf(plotCell);
  const baseLabel = bilingualKhatauniLabel(header?.label || cell.header_label || schemaKeyOf(cell) || 'Table value');
  const label = plot && schemaKeyOf(cell) !== 'plot_number' ? `${baseLabel} · Plot ${plot}` : baseLabel;
  return evidenceEntity(cell, 'cell', label, 1000 + rowOrder * 100 + cell.column_index, plot);
}
function collectEvidenceEntities(digitization) {
  const fields = digitization.items.filter(visibleReviewField).map((field, index) => evidenceEntity(
    field, 'field', bilingualKhatauniLabel(field.original_label || field.normalized_label || 'Field'), index,
  ));
  const rows = digitization.table?.rows || [];
  const cells = [];
  rows.forEach((row, rowOrder) => {
    row.cells.forEach((cell) => {
      const header = digitization.table?.headers?.find(candidate => candidate.column_index === cell.column_index);
      cells.push(cellEvidence(cell, row, header, rowOrder));
    });
  });
  return [...fields, ...cells];
}
function buildReviewIssues(entities, ruleValidation, crossValidation, structuredDuplicate) {
  const issues = new Map();
  const add = (entity, reason, priority, fallbackKey) => {
    const key = entity?.key || fallbackKey;
    if (!key) return;
    const existing = issues.get(key) || {
      key, evidence: entity || {key, entityType: 'record', entityId: key, label: 'Record-level review', boundingBox: null, order: 999999},
      reasons: new Set(), priority, order: entity?.order ?? 999999,
    };
    existing.priority = Math.min(existing.priority, priority);
    existing.reasons.add(reason);
    issues.set(key, existing);
  };
  const findEntity = ({field, scope, plotNumber, rowIndex}) => {
    if (scope === 'header' || scope === 'record') return entities.find(entity => entity.entityType === 'field' && entity.schemaKey === field);
    const plot = comparableValue(plotNumber);
    const rowCells = entities.filter(entity => entity.entityType === 'cell' && (
      plot ? comparableValue(entity.plotNumber) === plot : rowIndex !== null && rowIndex !== undefined ? entity.rowIndex === rowIndex : true
    ));
    return rowCells.find(entity => entity.schemaKey === field) || ((field === 'plot_number' || (!field && plot)) ? rowCells.find(entity => entity.schemaKey === 'plot_number') : null);
  };

  entities.forEach((entity) => {
    const status = entity.validation?.status;
    if (['NEEDS_REVIEW', 'UNRESOLVED'].includes(status)) add(entity, `Validation: ${status.replaceAll('_', ' ')}`, 1);
  });
  ruleValidation?.rules?.filter(rule => rule.status === 'REVIEW').forEach((rule, index) => {
    const entity = findEntity({field: rule.field, scope: rule.scope, plotNumber: rule.plot_number, rowIndex: rule.row_index});
    add(entity, rule.message || `${rule.name.replaceAll('_', ' ')} requires review`, 1, `rule:${rule.rule_id}:row:${rule.row_index ?? index}`);
  });
  crossValidation?.references?.forEach(reference => reference.differences?.forEach((difference, index) => {
    const entity = findEntity({field: difference.field, scope: difference.scope, plotNumber: difference.plot_number});
    add(entity, `Cross-record difference in ${difference.field.replaceAll('_', ' ')}`, 2, `cross:${reference.record_db_id}:${difference.field}:${index}`);
  }));
  entities.forEach((entity) => {
    if (entity.confidence !== null && entity.confidence !== undefined && entity.confidence < LOW_CONFIDENCE_THRESHOLD) {
      add(entity, `Low recognition evidence (${Math.round(entity.confidence)}%)`, 3);
    }
  });
  if (structuredDuplicate?.status === 'POSSIBLE_DUPLICATE') {
    add(null, 'Possible structured duplicate found in verified BhumiAI records', 4, 'record:structured-duplicate');
  }
  return [...issues.values()].map(issue => ({...issue, reasons: [...issue.reasons]})).sort(
    (left, right) => left.priority - right.priority || left.order - right.order || left.key.localeCompare(right.key),
  );
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

function ValidationIssueBadge({validation}) {
  const status = validation?.status;
  if (!status || status === 'PASS' || status === 'UNAVAILABLE') return null;
  return <span className={`rule-issue-badge ${status.toLowerCase().replaceAll('_', '-')}`}><AlertTriangle size={11}/>{status === 'UNRESOLVED' ? 'Unresolved' : `Rule check · ${status.replaceAll('_', ' ')}`}</span>;
}

function EvidenceButton({evidence, onSelect, compact = false}) {
  const available = Boolean(evidence.boundingBox);
  const label = `${available ? 'Show source evidence' : 'Source evidence unavailable'} for ${evidence.label}`;
  return <button type="button" className={`evidence-link ${compact ? 'compact' : ''} ${available ? 'available' : 'unavailable'}`} aria-label={label} title={label} onMouseDown={(event) => event.preventDefault()} onClick={(event) => { event.preventDefault(); event.stopPropagation(); onSelect(evidence); }}>{available ? <LocateFixed size={compact ? 14 : 12}/> : <span aria-hidden="true">⊘</span>}{!compact && available ? 'Show source' : null}</button>;
}

function ReviewIssueNavigator({issues, activeIndex, onNavigate}) {
  if (!issues.length) return <section className="review-issue-nav no-issues" aria-live="polite"><CheckCircle size={15}/><span>No review flags detected.</span></section>;
  const current = issues[Math.max(0, activeIndex)] || issues[0];
  return <section className="review-issue-nav" aria-label="Review issue navigation">
    <div><div className="eyebrow">REVIEW ISSUES</div><b>{issues.length} item{issues.length === 1 ? '' : 's'} require attention</b></div>
    <div className="review-issue-current"><small>Issue {Math.max(0, activeIndex) + 1} of {issues.length}</small><strong>{current.evidence.label}</strong><span>{current.reasons.join(' · ')}</span></div>
    <div className="review-issue-actions"><button type="button" onClick={() => onNavigate(Math.max(0, activeIndex) - 1)} disabled={activeIndex <= 0} aria-label="Previous review issue"><ChevronLeft size={14}/> Previous Issue</button><button type="button" onClick={() => onNavigate(Math.min(issues.length - 1, Math.max(0, activeIndex) + 1))} disabled={activeIndex >= issues.length - 1} aria-label="Next review issue">Next Issue <ChevronRight size={14}/></button></div>
  </section>;
}

function StructuredField({field, typingMode, work, drafts, selectedEvidence, onSelectEvidence, onFieldChange}) {
  const label = bilingualKhatauniLabel(field.original_label || field.normalized_label || 'Field');
  const draftKey = `field-${field.id}`;
  const evidence = {...evidenceEntity(field, 'field', label, field.display_order || 0), value: hasDraft(drafts, draftKey) ? drafts[draftKey] : valueOf(field)};
  const inputProps = {onFocus: () => onSelectEvidence(evidence), disabled: Boolean(work)};
  return <label className={`khatauni-field ${selectedEvidence?.key === evidence.key ? 'evidence-selected' : ''}`} data-field-id={field.id} data-evidence-entity={`field-${field.id}`}>
    <span>{label}</span>
    {supportsHindiPhoneticInput(label)
      ? <HindiPhoneticInput {...inputProps} key={`${field.id}-${valueOf(field)}`} defaultValue={valueOf(field)} hindiMode={typingMode === 'hi'} placeholder="स्वचालित रूप से पता नहीं चला / Not automatically detected" onValueChange={value => onFieldChange(field, value)} onCommit={value => value !== String(valueOf(field)) && onFieldChange(field, value)}/>
      : <input {...inputProps} key={`${field.id}-${valueOf(field)}`} defaultValue={valueOf(field)} placeholder="स्वचालित रूप से पता नहीं चला / Not automatically detected" onBlur={(event) => event.target.value !== String(valueOf(field)) && onFieldChange(field, event.target.value)}/>}
    <small className="recognition-indicators">{field.ai_confidence !== null && field.ai_confidence !== undefined && <ConfidenceBadge value={field.ai_confidence}/>}<ValidationIssueBadge validation={validationOf(field)}/><EvidenceButton evidence={evidence} onSelect={onSelectEvidence}/></small>
    {hasDraft(drafts, draftKey) && <em title={`Original OCR: ${ocrValueOf(field) || 'Blank'}`}><span className="edited-tag">Edited</span> Unsaved correction</em>}
    {field.officer_value !== null && field.officer_value !== undefined && <em><span className="edited-tag">Edited</span> OCR: {ocrValueOf(field) || 'रिक्त / Blank'}</em>}
  </label>;
}

function DigitalKhatauni({ digitization, digitizationLoading, work, isTerminal, typingMode, setTypingMode, drafts, isDirty, error, selectedEvidence, onSelectEvidence, onFieldChange, onCellChange, onAddRow, onDeleteRow, onSave, onNeedsReview, onVerify, onReject }) {
  const { items, table } = digitization;
  const visibleItems = items.filter(visibleReviewField);
  const coreItems = visibleItems.filter(field => CORE_FIELD_KEYS.has(schemaKeyOf(field))).sort((left, right) => CORE_FIELD_ORDER.indexOf(schemaKeyOf(left)) - CORE_FIELD_ORDER.indexOf(schemaKeyOf(right)));
  const additionalItems = visibleItems.filter(field => !CORE_FIELD_KEYS.has(schemaKeyOf(field)));
  const fieldGroups = groupedFields(coreItems);
  if (digitizationLoading) return <section className="card khatauni-pane khatauni-loading" aria-label="Loading structured record"><div className="section-head"><div><div className="eyebrow">DIGITAL KHATAUNI</div><h3>Loading structured record…</h3><p>The source record remains available while extracted fields load.</p></div></div><div className="khatauni-fields"><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/><span className="skeleton-block skeleton-khatauni-field"/></div><div className="skeleton-block skeleton-khatauni-table"/></section>;
  return <section className="card khatauni-pane structured-pane">
    <div className="section-head"><div><div className="eyebrow">STRUCTURED / EXTRACTED RECORD</div><h3>Structured Record</h3><p>Review and correct the extracted record beside the source document.</p></div>{!isTerminal && <div className="typing-mode" role="group" aria-label="Correction typing mode"><span>Typing</span><button type="button" className={typingMode === 'en' ? 'active' : ''} aria-pressed={typingMode === 'en'} onClick={() => setTypingMode('en')}>EN</button><button type="button" className={typingMode === 'hi' ? 'active' : ''} aria-pressed={typingMode === 'hi'} onClick={() => setTypingMode('hi')}>हिंदी</button></div>}</div>
    <div className="khatauni-fields" onChangeCapture={(event) => {
      const fieldId = event.target.closest('[data-field-id]')?.dataset.fieldId;
      const field = items.find((item) => String(item.id) === fieldId);
      if (field) onFieldChange(field, event.target.value);
    }}>
      {coreItems.length ? fieldGroups.map(([title, fields]) => <section className="field-group" key={title}><h4>{title}</h4>{fields.map((field) => <StructuredField key={field.id} field={field} typingMode={typingMode} work={work} drafts={drafts} selectedEvidence={selectedEvidence} onSelectEvidence={onSelectEvidence} onFieldChange={onFieldChange}/>)}</section>) : <div className="khatauni-empty">Extract Khatauni Data to create the core record fields.</div>}
      {additionalItems.length > 0 && <details className="secondary-record-fields"><summary>Additional record details <span>{additionalItems.length}</span></summary><div>{additionalItems.map(field => <StructuredField key={field.id} field={field} typingMode={typingMode} work={work} drafts={drafts} selectedEvidence={selectedEvidence} onSelectEvidence={onSelectEvidence} onFieldChange={onFieldChange}/>)}</div></details>}
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
          return <td key={header.column_index} className={cell && hasDraft(drafts, `cell-${cell.id}`) ? 'has-unsaved-correction' : ''}>{cell ? <div className="khatauni-cell">{supportsHindi ? <HindiPhoneticInput key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} hindiMode={typingMode === 'hi'} placeholder="मान दर्ज करें / Enter Value" onValueChange={value => onCellChange(cell, value)} onCommit={value => value !== String(valueOf(cell)) && onCellChange(cell, value)} disabled={Boolean(work)} /> : <input key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} placeholder="मान दर्ज करें / Enter Value" onBlur={(event) => event.target.value !== String(valueOf(cell)) && onCellChange(cell, event.target.value)} disabled={Boolean(work)} />}<span className="recognition-indicators">{cell.ai_confidence !== null && cell.ai_confidence !== undefined && <ConfidenceBadge value={cell.ai_confidence}/>}<ValidationIssueBadge validation={validationOf(cell)}/></span>{cell.officer_value !== null && cell.officer_value !== undefined && <small><span className="edited-tag">Edited</span> OCR: {ocrValueOf(cell) || 'रिक्त / Blank'}</small>}</div> : <span className="empty-cell">रिक्त / Blank</span>}</td>;
        })}<td><span className={`source-tag ${manual ? 'manual' : 'ocr'}`}>{manual ? 'Added by Officer' : 'OCR'}</span><button className="table-delete-button" type="button" onClick={() => onDeleteRow(row)} disabled={Boolean(work)}><Trash2 size={13} /> Delete row</button></td></tr>;
      }) : <tr><td colSpan={table.headers.length + 1} className="dynamic-empty-row">कोई पंक्ति विश्वसनीय रूप से नहीं मिली। सही पंक्ति अधिकारी जोड़ सकते हैं। / No row was detected reliably. An officer can add the correct row.</td></tr>}</tbody>
    </table></div> : <div className="khatauni-empty">No Khatauni table has been extracted yet.</div>}
    {!isTerminal && <footer className="review-action-footer" aria-label="Review actions"><div><span className="eyebrow">OFFICER CORRECTION</span><small>{isDirty ? 'Unsaved changes — save edits before recording a final decision.' : 'Save edits before recording a final decision.'}</small>{error && <p className="review-action-error" role="alert">{error}</p>}</div><div className="actions"><Button variant="secondary" onClick={onSave} loading={work === 'save-corrections'} loadingText="Saving…" disabled={!isDirty || Boolean(work)}><Save size={15} /> Save Corrections</Button><Button variant="secondary" onClick={onNeedsReview} disabled={isDirty || Boolean(work)}><AlertTriangle size={15} /> Needs Review</Button><Button onClick={onVerify} disabled={!items.length || !table || isDirty || Boolean(work)}><CheckCircle size={15} /> Verify Record</Button><Button variant="danger" onClick={onReject} disabled={isDirty || Boolean(work)}><XCircle size={15} /> Reject</Button></div></footer>}
  </section>;
}

function ParcelCell({cell, row, header, typingMode, work, drafts, selectedEvidence, onSelectEvidence, onCellChange, detail = false}) {
  if (!cell) return <span className="empty-cell">Blank</span>;
  const label = bilingualKhatauniLabel(header.label);
  const draftKey = `cell-${cell.id}`;
  const evidence = {...cellEvidence(cell, row, header), value: hasDraft(drafts, draftKey) ? drafts[draftKey] : valueOf(cell)};
  const inputProps = {onFocus: () => onSelectEvidence(evidence), disabled: Boolean(work)};
  return <div className={`khatauni-cell parcel-cell ${detail ? 'detail' : ''} ${selectedEvidence?.key === evidence.key ? 'evidence-selected' : ''}`} data-evidence-entity={`cell-${cell.id}`}>
    <div className="parcel-value-row">
      {supportsHindiPhoneticInput(label)
        ? <HindiPhoneticInput {...inputProps} key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} hindiMode={typingMode === 'hi'} placeholder="मान दर्ज करें / Enter value" onValueChange={value => onCellChange(cell, value)} onCommit={value => value !== String(valueOf(cell)) && onCellChange(cell, value)}/>
        : <input {...inputProps} key={`${cell.id}-${valueOf(cell)}`} defaultValue={valueOf(cell)} placeholder="Enter value" onChange={event => onCellChange(cell, event.target.value)}/>}
      <EvidenceButton evidence={evidence} onSelect={onSelectEvidence} compact/>
    </div>
    {cell.ai_confidence !== null && cell.ai_confidence !== undefined && <span className="cell-confidence"><ConfidenceBadge value={cell.ai_confidence}/></span>}
    {hasDraft(drafts, draftKey) && <small><span className="edited-tag">Edited</span> Unsaved</small>}
    {!hasDraft(drafts, draftKey) && cell.officer_value !== null && cell.officer_value !== undefined && <small title={`Original OCR: ${ocrValueOf(cell) || 'Blank'}`}><span className="edited-tag">Edited</span> OCR retained</small>}
  </div>;
}

function LandParcelReview({digitization, work, isTerminal, typingMode, drafts, selectedEvidence, reviewIssues, onSelectEvidence, onSelectIssue, onCellChange, onAddRow, onDeleteRow}) {
  const {table} = digitization;
  const [expandedRows, setExpandedRows] = useState({});
  if (!table) return <section className="card land-table-pane"><div className="section-head"><div><div className="eyebrow">LAND RECORD REVIEW</div><h3>Khatauni / Land Parcel Table</h3></div></div><div className="khatauni-empty">No Khatauni table has been extracted yet.</div></section>;
  const {primary, secondary} = parcelColumns(table);
  const toggleRow = rowIndex => setExpandedRows(current => ({...current, [rowIndex]: !current[rowIndex]}));
  return <section className="card land-table-pane">
    <div className="section-head land-table-head"><div><div className="eyebrow">LAND RECORD REVIEW</div><h3>Khatauni / Land Parcel Table</h3><p>Core parcel values stay visible; expand a row for secondary record details.</p></div>{!isTerminal && <Button variant="secondary" onClick={onAddRow} disabled={!table.id || Boolean(work)}><Plus size={14} /> Add Parcel</Button>}</div>
    <div className="table-wrap khatauni-table-wrap"><table className="data-table khatauni-table simplified-parcel-table">
      <thead><tr>{primary.map((header) => <th key={header.column_index}>{bilingualKhatauniLabel(header.label)}</th>)}<th>Review</th></tr></thead>
      <tbody>{table.rows.length ? table.rows.map((row) => {
        const manual = row.cells.length > 0 && row.cells.every((cell) => cell.confidence_source === 'officer_manual');
        const rowIssues = reviewIssues.filter(issue => issue.evidence.entityType === 'cell' && issue.evidence.rowIndex === row.row_index);
        const unresolved = rowIssues.some(issue => issue.reasons.some(reason => reason.toLowerCase().includes('unresolved')));
        const selectedInSecondary = selectedEvidence?.entityType === 'cell' && selectedEvidence.rowIndex === row.row_index && secondary.some(header => header.column_index === selectedEvidence.columnIndex);
        const expanded = Boolean(expandedRows[row.row_index] || selectedInSecondary);
        return <Fragment key={row.row_index}>
          <tr data-row-index={row.row_index}>{primary.map((header) => {
            const cell = row.cells.find(candidate => candidate.column_index === header.column_index);
            return <td key={header.column_index} className={cell && hasDraft(drafts, `cell-${cell.id}`) ? 'has-unsaved-correction' : ''}><ParcelCell cell={cell} row={row} header={header} typingMode={typingMode} work={work} drafts={drafts} selectedEvidence={selectedEvidence} onSelectEvidence={onSelectEvidence} onCellChange={onCellChange}/></td>;
          })}<td className="parcel-review-cell"><span className={`source-tag ${manual ? 'manual' : 'ocr'}`}>{manual ? 'Officer' : 'OCR'}</span>{rowIssues.length ? <button type="button" className={`row-review-status issue ${unresolved ? 'unresolved' : ''}`} onClick={() => onSelectIssue(rowIssues[0])}><AlertTriangle size={13}/>{unresolved ? 'Unresolved' : `${rowIssues.length} issue${rowIssues.length === 1 ? '' : 's'}`}</button> : <span className="row-review-status clear"><CheckCircle size={13}/> Clear</span>}{secondary.length > 0 && <button type="button" className="row-details-toggle" aria-expanded={expanded} onClick={() => toggleRow(row.row_index)}>{expanded ? 'Hide details' : 'View details'}</button>}{!isTerminal && <button className="table-delete-button compact" type="button" onClick={() => onDeleteRow(row)} disabled={Boolean(work)} aria-label={`Delete parcel row ${row.row_index + 1}`}><Trash2 size={13}/> Delete</button>}</td></tr>
          {expanded && secondary.length > 0 && <tr className="parcel-detail-row"><td colSpan={primary.length + 1}><div className="parcel-detail-grid">{secondary.map(header => {
            const cell = row.cells.find(candidate => candidate.column_index === header.column_index);
            return <div className="parcel-detail-field" key={header.column_index}><span>{bilingualKhatauniLabel(header.label)}</span><ParcelCell cell={cell} row={row} header={header} typingMode={typingMode} work={work} drafts={drafts} selectedEvidence={selectedEvidence} onSelectEvidence={onSelectEvidence} onCellChange={onCellChange} detail/></div>;
          })}</div></td></tr>}
        </Fragment>;
      }) : <tr><td colSpan={primary.length + 1} className="dynamic-empty-row">No row was detected reliably. An officer can add the correct row.</td></tr>}</tbody>
    </table></div>
  </section>;
}

function OfficerDecisionPanel({digitization, drafts, reviewIssues, isDirty, error, work, isTerminal, onSave, onNeedsReview, onVerify, onReject}) {
  if (isTerminal) return null;
  const entries = [...digitization.items.filter(visibleReviewField), ...(digitization.table?.cells || [])];
  const edited = new Set([...Object.keys(drafts), ...entries.filter((entry) => entry.officer_value !== null && entry.officer_value !== undefined).map((entry) => `${entry.table_id ? 'cell' : 'field'}-${entry.id}`)]).size;
  const lowConfidence = entries.filter((entry) => entry.ai_confidence !== null && entry.ai_confidence !== undefined && entry.ai_confidence < 65).length;
  return <aside className="card officer-decision-panel" aria-label="Officer decision">
    <div className="officer-decision-head"><div className="eyebrow">OFFICER REVIEW</div><h3>Decision</h3></div>
    <dl className="decision-summary"><div><dt>Edited fields</dt><dd>{edited}</dd></div><div><dt>Low evidence</dt><dd>{lowConfidence}</dd></div><div><dt>Review issues</dt><dd>{reviewIssues.length}</dd></div></dl>
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
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [activeIssueKey, setActiveIssueKey] = useState('');
  const hasRawOcr = Boolean(ocr?.raw_text?.trim());
  const hasExtraction = digitization.items.length > 0 && Boolean(digitization.table);
  const isDirty = structuralDirty || Object.keys(drafts).length > 0;
  const evidenceEntities = useMemo(() => collectEvidenceEntities(digitization), [digitization]);
  const reviewIssues = useMemo(
    () => buildReviewIssues(evidenceEntities, ruleValidation, crossValidation, structuredDuplicate),
    [evidenceEntities, ruleValidation, crossValidation, structuredDuplicate],
  );
  const activeIssueIndex = Math.max(0, reviewIssues.findIndex(issue => issue.key === activeIssueKey));

  useEffect(() => {
    if (!isDirty) return undefined;
    const warnBeforeUnload = (event) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [isDirty]);

  useEffect(() => {
    if (!reviewIssues.length) {
      setActiveIssueKey('');
      setSelectedEvidence(current => current?.selectionSource === 'issue' ? null : current);
      return;
    }
    const activeIssue = reviewIssues.find(issue => issue.key === activeIssueKey);
    if (activeIssue) {
      setSelectedEvidence(current => {
        if (current?.selectionSource !== 'issue' || current.key !== activeIssue.evidence.key) return current;
        const sameReasons = (current.reasons || []).join('\n') === activeIssue.reasons.join('\n');
        const sameValue = current.value === activeIssue.evidence.value && current.validation === activeIssue.evidence.validation;
        return sameReasons && sameValue ? current : {...activeIssue.evidence, reasons: activeIssue.reasons, selectionSource: 'issue'};
      });
      return;
    }
    const first = reviewIssues[0];
    setActiveIssueKey(first.key);
    setSelectedEvidence({...first.evidence, reasons: first.reasons, selectionSource: 'issue'});
    scrollStructuredEvidence(first.evidence);
  }, [reviewIssues, activeIssueKey]);

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
    setSelectedEvidence(current => current?.key === `${kind}:${entry.id}` ? {...current, value} : current);
  }

  function scrollStructuredEvidence(evidence) {
    if (!evidence || evidence.entityType === 'record') return;
    window.requestAnimationFrame(() => {
      const target = window.document.querySelector(`[data-evidence-entity="${evidence.entityType}-${evidence.entityId}"]`);
      const disclosure = target?.closest('details');
      if (disclosure && !disclosure.open) disclosure.open = true;
      const scroller = target?.closest(evidence.entityType === 'cell' ? '.khatauni-table-wrap' : '.structured-pane');
      if (!target || !scroller) return;
      const targetRect = target.getBoundingClientRect();
      const scrollerRect = scroller.getBoundingClientRect();
      scroller.scrollTo({
        top: Math.max(0, scroller.scrollTop + targetRect.top - scrollerRect.top - scroller.clientHeight / 2 + targetRect.height / 2),
        left: Math.max(0, scroller.scrollLeft + targetRect.left - scrollerRect.left - scroller.clientWidth / 2 + targetRect.width / 2),
        behavior: 'smooth',
      });
    });
  }

  function selectEvidence(evidence) {
    const matchingIssue = reviewIssues.find(issue => issue.evidence.key === evidence.key);
    setSelectedEvidence({...evidence, reasons: matchingIssue?.reasons || [], selectionSource: 'manual'});
    if (matchingIssue) setActiveIssueKey(matchingIssue.key);
    scrollStructuredEvidence(evidence);
  }

  function navigateReviewIssue(index) {
    const issue = reviewIssues[index];
    if (!issue) return;
    setActiveIssueKey(issue.key);
    setSelectedEvidence({...issue.evidence, reasons: issue.reasons, selectionSource: 'issue'});
    scrollStructuredEvidence(issue.evidence);
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
    <ReviewIssueNavigator issues={reviewIssues} activeIndex={activeIssueIndex} onNavigate={navigateReviewIssue}/>
    <div className="review-workbench"><SourceDocument document={sourceDocument} processedPath={processedPath} sourceMode={sourceMode} setSourceMode={setSourceMode} zoom={zoom} setZoom={setZoom} fit={fit} setFit={setFit} processingActions={processingActions} selectedEvidence={selectedEvidence}/><DigitalKhatauni digitization={digitization} digitizationLoading={isTerminal ? false : digitizationLoading} work={isTerminal ? 'read-only' : work} isTerminal={isTerminal} typingMode={typingMode} setTypingMode={setTypingMode} drafts={drafts} isDirty={isDirty} error={error} selectedEvidence={selectedEvidence} onSelectEvidence={selectEvidence} onFieldChange={updateField} onCellChange={updateCell} onAddRow={addRow} onDeleteRow={deleteRow} onSave={saveCorrections} onNeedsReview={() => isDirty ? setError('Save unsaved corrections before updating this review.') : setPendingDecision('mark-review')} onVerify={() => isDirty ? setError('Save unsaved corrections before verifying this record.') : setPendingDecision('approve')} onReject={() => isDirty ? setError('Save unsaved corrections before rejecting this record.') : setRejectOpen(true)} /></div>
    <section className={`land-review-layout ${isTerminal ? 'terminal-land-review' : ''}`}><LandParcelReview digitization={digitization} work={isTerminal ? 'read-only' : work} isTerminal={isTerminal} typingMode={typingMode} drafts={drafts} selectedEvidence={selectedEvidence} reviewIssues={reviewIssues} onSelectEvidence={selectEvidence} onSelectIssue={(issue) => navigateReviewIssue(reviewIssues.findIndex(candidate => candidate.key === issue.key))} onCellChange={updateCell} onAddRow={addRow} onDeleteRow={deleteRow}/><OfficerDecisionPanel digitization={digitization} drafts={drafts} reviewIssues={reviewIssues} isDirty={isDirty} error={error} work={work} isTerminal={isTerminal} onSave={saveCorrections} onNeedsReview={() => isDirty ? setError('Save unsaved corrections before updating this review.') : setPendingDecision('mark-review')} onVerify={() => isDirty ? setError('Save unsaved corrections before verifying this record.') : setPendingDecision('approve')} onReject={() => isDirty ? setError('Save unsaved corrections before rejecting this record.') : setRejectOpen(true)}/></section>

    {pendingDecision && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="decision-title"><div className="modal-card decision-modal"><div className="eyebrow">OFFICER DECISION</div><h3 id="decision-title">{pendingDecision === 'approve' ? 'Verify this record?' : 'Mark this record for further review?'}</h3><p><b>Submission #{submission.id || sourceDocument.id}</b></p><p>{pendingDecision === 'approve' ? 'Final decision: verification creates or updates the verified digital record using the reviewed values.' : 'The record remains in the review queue for a later decision.'}</p>{error && <p className="review-action-error" role="alert">{error}</p>}<div className="actions"><Button variant="secondary" onClick={() => setPendingDecision('')} disabled={Boolean(work)}>Cancel</Button><Button onClick={() => decide(pendingDecision)} loading={work === pendingDecision} loadingText={pendingDecision === 'approve' ? 'Verifying…' : 'Updating…'} disabled={Boolean(work)}>{pendingDecision === 'approve' ? 'Verify Record' : 'Mark Needs Review'}</Button></div></div></div>}
    {rejectOpen && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="reject-title"><div className="modal-card decision-modal"><div className="eyebrow">OFFICER DECISION</div><h3 id="reject-title">Reject this record?</h3><p><b>Submission #{submission.id || sourceDocument.id}</b></p><p>Final decision: rejection is recorded in the audit trail and shown to the submitting citizen.</p><div className="field"><label>Reason Category</label><select value={reasonCategory} onChange={event => setReasonCategory(event.target.value)} disabled={Boolean(work)}><option value="">Select a reason</option>{['Poor Scan Quality', 'Incomplete Document', 'Incorrect Document', 'Unreadable Information', 'Duplicate Submission', 'Information Mismatch', 'Other'].map(reason => <option key={reason}>{reason}</option>)}</select></div><div className="field"><label>Officer Note {reasonCategory === 'Other' ? '(required)' : '(optional)'}</label><textarea value={officerNote} onChange={event => setOfficerNote(event.target.value)} placeholder="Explain what the citizen needs to correct." disabled={Boolean(work)}/></div>{error && <p className="review-action-error" role="alert">{error}</p>}<div className="actions" style={{marginTop: 16}}><Button variant="secondary" onClick={() => setRejectOpen(false)} disabled={Boolean(work)}>Cancel</Button><Button variant="danger" loading={work === 'reject'} loadingText="Rejecting…" disabled={!reasonCategory || (reasonCategory === 'Other' && !officerNote.trim()) || Boolean(work)} onClick={() => decide('reject', {reason_category: reasonCategory, officer_note: officerNote.trim() || null})}>Confirm rejection</Button></div></div></div>}
    {pendingDeleteRow && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="delete-row-title"><div className="modal-card decision-modal"><div className="eyebrow">TABLE CORRECTION</div><h3 id="delete-row-title">Remove row {pendingDeleteRow.row_index + 1}?</h3><p>This removes the row from the digital record and records the action in the audit trail.</p><div className="actions"><Button variant="secondary" onClick={() => setPendingDeleteRow(null)}>Cancel</Button><Button variant="danger" onClick={() => { const row = pendingDeleteRow; setPendingDeleteRow(null); mutate('delete-row', () => api.deleteDynamicTableRow(id, digitization.table.id, row.row_index), 'Khatauni row removed and audited.'); }} loading={work === 'delete-row'} loadingText="Removing…">Remove row</Button></div></div></div>}
  </>;
}
