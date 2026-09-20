export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {credentials: 'include', ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || 'The request could not be completed.');
  return data;
}

const jsonRequest = (method, payload) => ({
  method,
  headers: {'Content-Type':'application/json'},
  body: JSON.stringify(payload),
});

export const api = {
  login: (payload) => request('/api/auth/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) }),
  register: (payload) => request('/api/auth/register', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) }),
  googleExchange: (ticket) => request('/api/auth/google/exchange', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ticket}) }),
  me: () => request('/api/auth/me'),
  logout: () => request('/api/auth/logout', {method:'POST'}),
  requestPhoneOtp: (phone_number) => request('/api/auth/phone/request-otp', jsonRequest('POST', {phone_number})),
  verifyPhoneOtp: (phone_number, otp) => request('/api/auth/phone/verify-otp', jsonRequest('POST', {phone_number, otp})),
  updateProfile: (payload) => request('/api/auth/profile', jsonRequest('PUT', payload)),
  requestEmailVerification: () => request('/api/auth/email/request-verification', {method:'POST'}),
  verifyEmail: (code) => request('/api/auth/email/verify', jsonRequest('POST', {code})),
  userDashboard: () => request('/api/user/dashboard'),
  userSubmissions: ({status = '', search = ''} = {}) => request(`/api/user/submissions?${new URLSearchParams({...(status ? {status} : {}), ...(search ? {search} : {})})}`),
  officerDashboard: () => request('/api/officer/dashboard'),
  submissions: ({status = '', search = ''} = {}) => request(`/api/officer/submissions?${new URLSearchParams({...(status ? {status} : {}), ...(search ? {search} : {})})}`),
  submission: (id) => request(`/api/officer/submissions/${id}`),
  preprocess: (id) => request(`/api/officer/documents/${id}/preprocess`, {method:'POST'}),
  ocr: (id, processedPath) => request(`/api/officer/documents/${id}/ocr?processed_path=${encodeURIComponent(processedPath || '')}`, {method:'POST'}),
  extract: (id, ocrId) => request(`/api/officer/documents/${id}/extract?ocr_id=${ocrId}`, {method:'POST'}),
  fields: (id) => request(`/api/officer/documents/${id}/fields`),
  latestOcr: (id) => request(`/api/officer/documents/${id}/ocr/latest`),
  updateField: (id, fieldId, officer_value) => request(`/api/officer/documents/${id}/fields/${fieldId}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({officer_value})}),
  // Dynamic digitization keeps the labels and tabular layout detected for this
  // particular document. These helpers deliberately do not impose a land-record
  // schema on the client.
  digitization: (id) => request(`/api/officer/documents/${id}/digitization`),
  createDynamicField: (id, payload) => request(`/api/officer/documents/${id}/dynamic-fields`, jsonRequest('POST', payload)),
  updateDynamicField: (id, fieldId, payload) => request(`/api/officer/documents/${id}/dynamic-fields/${fieldId}`, jsonRequest('PATCH', payload)),
  deleteDynamicField: (id, fieldId) => request(`/api/officer/documents/${id}/dynamic-fields/${fieldId}`, {method:'DELETE'}),
  createDynamicTable: (id, payload) => request(`/api/officer/documents/${id}/tables`, jsonRequest('POST', payload)),
  updateDynamicTable: (id, tableId, payload) => request(`/api/officer/documents/${id}/tables/${tableId}`, jsonRequest('PATCH', payload)),
  createDynamicTableRow: (id, tableId, payload) => request(
    `/api/officer/documents/${id}/tables/${tableId}/rows`,
    payload && Object.keys(payload).length ? jsonRequest('POST', payload) : {method:'POST'},
  ),
  updateDynamicTableCell: (id, tableId, cellId, payload) => request(`/api/officer/documents/${id}/tables/${tableId}/cells/${cellId}`, jsonRequest('PATCH', payload)),
  deleteDynamicTableRow: (id, tableId, rowId) => request(`/api/officer/documents/${id}/tables/${tableId}/rows/${rowId}`, {method:'DELETE'}),
  deleteDynamicTableCell: (id, tableId, cellId) => request(`/api/officer/documents/${id}/tables/${tableId}/cells/${cellId}`, {method:'DELETE'}),
  decision: (id, action, payload) => request(`/api/officer/documents/${id}/${action}`, payload ? jsonRequest('POST', payload) : {method:'POST'}),
  duplicateCheck: (id) => request(`/api/documents/${id}/duplicate-check`, {method:'POST'}),
  duplicateContinue: (id, matchedDocumentId) => request(`/api/documents/${id}/duplicate-continue?matched_document_id=${encodeURIComponent(matchedDocumentId)}`, {method:'POST'}),
  notifications: () => request(`/api/user/notifications`),
  markNotificationRead: (notificationId) => request(`/api/user/notifications/${notificationId}/read`, {method:'PATCH'}),
  records: (search='') => request(`/api/verified-records/?search=${encodeURIComponent(search)}`),
  record: (id) => request(`/api/verified-records/${id}`),
  audit: () => request('/api/officer/audit'),
  officerUpload: (formData) => request('/api/documents/officer-upload', {method:'POST', body:formData}),
};
