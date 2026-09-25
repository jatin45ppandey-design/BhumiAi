export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {credentials: 'include', ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || 'The request could not be completed.');
  return data;
}

async function requestBlob(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {credentials: 'include', ...options});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || data.message || 'The document could not be loaded.');
  }
  return response.blob();
}

const jsonRequest = (method, payload) => ({
  method,
  headers: {'Content-Type':'application/json'},
  body: JSON.stringify(payload),
});

export const api = {
  login: (payload) => request('/api/auth/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) }),
  me: () => request('/api/auth/me'),
  logout: () => request('/api/auth/logout', {method:'POST'}),
  requestPhoneOtp: (phone_number, intent) => request('/api/auth/phone/request-otp', jsonRequest('POST', {phone_number, intent})),
  verifyPhoneOtp: (phone_number, otp, intent) => request('/api/auth/phone/verify-otp', jsonRequest('POST', {phone_number, otp, intent})),
  updateProfile: (payload) => request('/api/auth/profile', jsonRequest('PUT', payload)),
  requestEmailVerification: () => request('/api/auth/email/request-verification', {method:'POST'}),
  verifyEmail: (code) => request('/api/auth/email/verify', jsonRequest('POST', {code})),
  userDashboard: () => request('/api/user/dashboard'),
  userSubmissions: ({status = '', search = ''} = {}) => request(`/api/user/submissions?${new URLSearchParams({...(status ? {status} : {}), ...(search ? {search} : {})})}`),
  officerDashboard: () => request('/api/officer/dashboard'),
  aiFeedbackSummary: () => request('/api/officer/ai-feedback/summary'),
  submissions: ({status = '', search = '', documentId = ''} = {}) => request(`/api/officer/submissions?${new URLSearchParams({...(status ? {status} : {}), ...(search ? {search} : {}), ...(documentId ? {document_id: documentId} : {})})}`),
  preprocess: (id) => request(`/api/officer/documents/${id}/preprocess`, {method:'POST'}),
  ocr: (id, processedPath) => request(`/api/officer/documents/${id}/ocr?processed_path=${encodeURIComponent(processedPath || '')}`, {method:'POST'}),
  extract: (id, ocrId) => request(`/api/officer/documents/${id}/extract?ocr_id=${ocrId}`, {method:'POST'}),
  latestOcr: (id) => request(`/api/officer/documents/${id}/ocr/latest`),
  // Dynamic digitization keeps the labels and tabular layout detected for this
  // particular document. These helpers deliberately do not impose a land-record
  // schema on the client.
  digitization: (id) => request(`/api/officer/documents/${id}/digitization`),
  ruleValidation: (id) => request(`/api/officer/documents/${id}/rule-validation`),
  crossRecordValidation: (id) => request(`/api/officer/documents/${id}/cross-record-validation`),
  structuredDuplicateCheck: (id) => request(`/api/officer/documents/${id}/structured-duplicate-check`),
  updateDynamicField: (id, fieldId, payload) => request(`/api/officer/documents/${id}/dynamic-fields/${fieldId}`, jsonRequest('PATCH', payload)),
  createDynamicTableRow: (id, tableId, payload) => request(
    `/api/officer/documents/${id}/tables/${tableId}/rows`,
    payload && Object.keys(payload).length ? jsonRequest('POST', payload) : {method:'POST'},
  ),
  updateDynamicTableCell: (id, tableId, cellId, payload) => request(`/api/officer/documents/${id}/tables/${tableId}/cells/${cellId}`, jsonRequest('PATCH', payload)),
  deleteDynamicTableRow: (id, tableId, rowId) => request(`/api/officer/documents/${id}/tables/${tableId}/rows/${rowId}`, {method:'DELETE'}),
  decision: (id, action, payload) => request(`/api/officer/documents/${id}/${action}`, payload ? jsonRequest('POST', payload) : {method:'POST'}),
  duplicateCheck: (id) => request(`/api/documents/${id}/duplicate-check`, {method:'POST'}),
  duplicateContinue: (id, matchedDocumentId) => request(`/api/documents/${id}/duplicate-continue?matched_document_id=${encodeURIComponent(matchedDocumentId)}`, {method:'POST'}),
  notifications: () => request(`/api/user/notifications`),
  records: (search='') => request(`/api/verified-records/?search=${encodeURIComponent(search)}`),
  record: (id) => request(`/api/verified-records/${id}`),
  documentContent: (id, variant = 'original') => requestBlob(`/api/documents/${id}/content?variant=${encodeURIComponent(variant)}`),
  officerUpload: (formData) => request('/api/documents/officer-upload', {method:'POST', body:formData}),
};
