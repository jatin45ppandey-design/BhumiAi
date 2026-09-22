const actionLabels = {
  DOCUMENT_UPLOADED: 'Document uploaded',
  SUBMITTED_TO_OFFICER: 'Submitted for officer review',
  PREPROCESS_COMPLETED: 'Document prepared',
  OCR_STARTED: 'Text extraction started',
  OCR_COMPLETED: 'Text extraction completed',
  OCR_FAILED: 'Text extraction needs attention',
  KHATAUNI_EXTRACTION_COMPLETED: 'Structured record prepared',
  FIELD_EDITED: 'Corrections saved',
  VERIFIED: 'Record verified',
  REJECTED: 'Record rejected',
  NEEDS_REVIEW: 'Marked for further review',
  DUPLICATE_CHECKED: 'Duplicate review performed',
  DUPLICATE_OVERRIDE_CONTINUE: 'Duplicate review continued',
  ROW_ADDED_MANUALLY: 'Table row added',
  ROW_REMOVED: 'Table row removed',
  'Legacy field edited': 'Corrections saved',
  'Dynamic field added': 'Field added',
  'Dynamic field deleted': 'Field removed',
  'Dynamic table added': 'Table added',
  'Table headers edited': 'Table headers updated',
  'Table cell removed': 'Table cell removed',
  RECORD_EXPORTED: 'Record exported',
};

const actionDescriptions = {
  DOCUMENT_UPLOADED: 'A land-record document was added to the workspace.',
  SUBMITTED_TO_OFFICER: 'The submission was sent for verification.',
  DUPLICATE_CHECKED: 'A possible duplicate was checked.',
  DUPLICATE_OVERRIDE_CONTINUE: 'Duplicate review was completed and the record continued.',
  PREPROCESS_COMPLETED: 'The document was prepared for text extraction.',
  OCR_STARTED: 'Text extraction started for this document.',
  OCR_COMPLETED: 'Text was extracted from the document.',
  OCR_FAILED: 'Text extraction needs attention before review can continue.',
  KHATAUNI_EXTRACTION_COMPLETED: 'A structured record was prepared from the extracted text.',
  FIELD_EDITED: 'A record correction was saved.',
  ROW_ADDED_MANUALLY: 'A table row was added during review.',
  ROW_REMOVED: 'A table row was removed during review.',
  'Legacy field edited': 'A record correction was saved.',
  'Dynamic field added': 'A field was added during review.',
  'Dynamic field deleted': 'A field was removed during review.',
  'Dynamic table added': 'A table was added during review.',
  'Table headers edited': 'Table headers were updated during review.',
  'Table cell removed': 'A table cell was removed during review.',
  VERIFIED: 'The record was verified and added to the verified repository.',
  REJECTED: 'The record was rejected for correction or resubmission.',
  NEEDS_REVIEW: 'The record was marked for further review.',
  RECORD_EXPORTED: 'A verified record was exported.',
};

const workLogActions = new Set(Object.keys(actionDescriptions));

export function isWorkLogEvent(event) {
  return workLogActions.has(event?.action);
}

export function activityLabel(action = '') {
  if (actionLabels[action]) return actionLabels[action];
  return action.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase()) || 'Record updated';
}

export function activityDescription(event) {
  return actionDescriptions[event.action] || `${activityLabel(event.action)} was recorded.`;
}

export function activityReference(event) {
  if (event.submission_id && event.document_id) return `Submission #${event.submission_id} · Record #${event.document_id}`;
  if (event.record_id) return `Verified record #${event.record_id}`;
  if (event.document_id) return `Record #${event.document_id}`;
  if (event.submission_id) return `Submission #${event.submission_id}`;
  return '—';
}

export function actorLabel(event) {
  let role = '';
  try { role = JSON.parse(event.metadata_json || '{}').actor_role || ''; } catch { /* Older audit entries may not contain JSON. */ }
  if (role.toLowerCase() === 'officer') return 'Officer';
  if (role.toLowerCase() === 'citizen') return 'Citizen';
  if (!event.user_id) return 'System';
  return ['DOCUMENT_UPLOADED', 'SUBMITTED_TO_OFFICER'].includes(event.action) ? 'Citizen' : 'Officer';
}
