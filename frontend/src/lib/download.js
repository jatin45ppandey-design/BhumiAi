import {API_URL} from './api';

const fallbackName = (value) => String(value || 'BhumiAI_verified_record')
  .replace(/[\\/:*?"<>|\x00-\x1F]+/g, '_')
  .replace(/^\.+/, '')
  .slice(0, 180) || 'BhumiAI_verified_record';

function filenameFrom(response, fallback) {
  const disposition = response.headers.get('content-disposition') || '';
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded) {
    try { return fallbackName(decodeURIComponent(encoded[1])); }
    catch { return fallbackName(fallback); }
  }
  const quoted = disposition.match(/filename\s*=\s*"([^"]+)"/i);
  const plain = disposition.match(/filename\s*=\s*([^;\s]+)/i);
  return fallbackName((quoted || plain || [])[1] || fallback);
}

async function responseMessage(response) {
  const payload = await response.json().catch(() => null);
  if (response.status === 401) return 'Your session has expired. Please sign in again.';
  if (response.status === 403) return 'You are not authorized to export this record.';
  if (response.status === 409) return 'This record is not verified, so export is unavailable.';
  return payload?.detail || payload?.message || 'Export failed. Please try again.';
}

/** Download an authenticated export response without duplicating browser logic in pages. */
export async function downloadAuthenticated(path, fallbackFilename) {
  const response = await fetch(`${API_URL}${path}`, {credentials: 'include'});
  if (!response.ok) {
    const error = new Error(await responseMessage(response));
    error.status = response.status;
    throw error;
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filenameFrom(response, fallbackFilename);
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  return {filename: anchor.download};
}
