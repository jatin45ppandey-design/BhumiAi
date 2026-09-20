export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || 'The request could not be completed.');
  return data;
}

const jsonRequest = (method, payload) => ({
  method,
  headers: {'Content-Type':'application/json'},
  body: JSON.stringify(payload),
});

const officerQuery = (officerId) => officerId ? `?officer_id=${encodeURIComponent(officerId)}` : '';

export const api = {
  login: (payload) => request('/api/auth/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) }),
  register: (payload) => request('/api/auth/register', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) }),
  googleExchange: (ticket) => request('/api/auth/google/exchange', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ticket}) }),
  userDashboard: (id) => request(`/api/user/dashboard?user_id=${id}`),
  userSubmissions: (id) => request(`/api/user/submissions?user_id=${id}`),
  officerDashboard: () => request('/api/officer/dashboard'),
  submissions: () => request('/api/officer/submissions'),
  submission: (id) => request(`/api/officer/submissions/${id}`),
  preprocess: (id) => request(`/api/officer/documents/${id}/preprocess`, {method:'POST'}),
  ocr: (id, processedPath) => request(`/api/officer/documents/${id}/ocr?processed_path=${encodeURIComponent(processedPath || '')}`, {method:'POST'}),
  extract: (id, ocrId) => request(`/api/officer/documents/${id}/extract?ocr_id=${ocrId}`, {method:'POST'}),
  fields: (id) => request(`/api/officer/documents/${id}/fields`),
  latestOcr: (id) => request(`/api/officer/documents/${id}/ocr/latest`),
  updateField: (id, fieldId, officerId, officer_value) => request(`/api/officer/documents/${id}/fields/${fieldId}?officer_id=${officerId}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({officer_value})}),
  // Dynamic digitization keeps the labels and tabular layout detected for this
  // particular document. These helpers deliberately do not impose a land-record
  // schema on the client.
  digitization: (id) => request(`/api/officer/documents/${id}/digitization`),
  createDynamicField: (id, payload, officerId) => request(`/api/officer/documents/${id}/dynamic-fields${officerQuery(officerId)}`, jsonRequest('POST', payload)),
  updateDynamicField: (id, fieldId, payload, officerId) => request(`/api/officer/documents/${id}/dynamic-fields/${fieldId}${officerQuery(officerId)}`, jsonRequest('PATCH', payload)),
  deleteDynamicField: (id, fieldId, officerId) => request(`/api/officer/documents/${id}/dynamic-fields/${fieldId}${officerQuery(officerId)}`, {method:'DELETE'}),
  createDynamicTable: (id, payload, officerId) => request(`/api/officer/documents/${id}/tables${officerQuery(officerId)}`, jsonRequest('POST', payload)),
  updateDynamicTable: (id, tableId, payload, officerId) => request(`/api/officer/documents/${id}/tables/${tableId}${officerQuery(officerId)}`, jsonRequest('PATCH', payload)),
  createDynamicTableRow: (id, tableId, payload, officerId) => request(
    `/api/officer/documents/${id}/tables/${tableId}/rows${officerQuery(officerId)}`,
    payload && Object.keys(payload).length ? jsonRequest('POST', payload) : {method:'POST'},
  ),
  updateDynamicTableCell: (id, tableId, cellId, payload, officerId) => request(`/api/officer/documents/${id}/tables/${tableId}/cells/${cellId}${officerQuery(officerId)}`, jsonRequest('PATCH', payload)),
  deleteDynamicTableRow: (id, tableId, rowId, officerId) => request(`/api/officer/documents/${id}/tables/${tableId}/rows/${rowId}${officerQuery(officerId)}`, {method:'DELETE'}),
  deleteDynamicTableCell: (id, tableId, cellId, officerId) => request(`/api/officer/documents/${id}/tables/${tableId}/cells/${cellId}${officerQuery(officerId)}`, {method:'DELETE'}),
  decision: (id, action, officerId) => request(`/api/officer/documents/${id}/${action}?officer_id=${officerId}`, {method:'POST'}),
  records: (search='') => request(`/api/verified-records/?search=${encodeURIComponent(search)}`),
  record: (id) => request(`/api/verified-records/${id}`),
  audit: () => request('/api/officer/audit'),
  officerUpload: (formData) => request('/api/documents/officer-upload', {method:'POST', body:formData}),
};
