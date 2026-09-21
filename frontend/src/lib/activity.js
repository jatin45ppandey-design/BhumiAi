const actionLabels = {
  DOCUMENT_UPLOADED: 'Document uploaded',
  SUBMITTED_TO_OFFICER: 'Submitted for officer review',
  PREPROCESS_COMPLETED: 'Document prepared',
  OCR_STARTED: 'Text extraction started',
  OCR_COMPLETED: 'Text extraction completed',
  OCR_FAILED: 'Text extraction needs attention',
  KHATAUNI_EXTRACTION_COMPLETED: 'Structured record prepared',
  FIELD_EDITED: 'Correction saved',
  VERIFIED: 'Record verified',
  REJECTED: 'Record rejected',
  NEEDS_REVIEW: 'Marked for further review',
  DUPLICATE_CHECKED: 'Duplicate review performed',
  DUPLICATE_OVERRIDE_CONTINUE: 'Duplicate review continued',
  ROW_ADDED_MANUALLY: 'Table row added',
  ROW_REMOVED: 'Table row removed',
};

export function activityLabel(action = '') {
  if (actionLabels[action]) return actionLabels[action];
  return action.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase()) || 'Record updated';
}

export function activityDescription(event) {
  const label = activityLabel(event.action);
  const reference = event.document_id ? `Record #${event.document_id}` : event.submission_id ? `Submission #${event.submission_id}` : 'BhumiAI workspace';
  return `${label} · ${reference}`;
}

export function actorLabel(event) {
  if (!event.user_id) return 'System';
  let role = '';
  try { role = JSON.parse(event.metadata_json || '{}').actor_role || ''; } catch { /* Older audit entries may not contain JSON. */ }
  const label = role.toLowerCase() === 'officer' ? 'Officer' : role.toLowerCase() === 'citizen' ? 'Citizen' : 'Account';
  return `${label} #${event.user_id}`;
}
