'use client';

import {useEffect, useRef, useState} from 'react';
import {useRouter} from 'next/navigation';
import {Camera, FileText, UploadCloud, X} from 'lucide-react';
import {api} from '../../../lib/api';
import CameraCapture from '../../../components/upload/CameraCapture';
import {Button, ErrorMessage} from '../../../components/common/UI';

export default function OfficerUpload() {
  const [file, setFile] = useState(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const inputRef = useRef(null);
  const router = useRouter();
  const selectFile = nextFile => { setFile(nextFile || null); setError(''); };
  const pick = event => selectFile(event.target.files?.[0]);
  const replaceFile = () => { selectFile(null); if (inputRef.current) inputRef.current.value = ''; };

  useEffect(() => {
    if (!file?.type?.startsWith('image/')) { setPreviewUrl(''); return undefined; }
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  async function upload() {
    if (loading) return;
    const form = document.querySelector('#officer-upload-form');
    if (!file || !form.reportValidity()) return;
    setLoading('upload'); setError('');
    try {
      const data = new FormData(form);
      data.append('file', file);
      const result = await api.officerUpload(data);
      router.push(`/officer/review/${result.document_id}`);
    } catch (uploadError) { setError(uploadError.message); }
    finally { setLoading(''); }
  }

  return <>
    <div className="page-title officer-page-title"><div><div className="eyebrow">OFFICER WORKSPACE</div><h2>Digitize a walk-in land record</h2><p>Capture or upload a physical record, then process it through the standard officer review workflow.</p></div></div>
    <ErrorMessage>{error}</ErrorMessage>
    <div className="split upload-layout officer-upload-layout">
      <section className="card upload-card source-upload-card"><div className="section-head"><div><div className="eyebrow">SOURCE DOCUMENT</div><h3>Upload document</h3><p>Choose a file or take a clear photo of the physical record.</p></div></div><div className="source-choice-grid"><button type="button" className="source-choice" onClick={() => inputRef.current?.click()} disabled={Boolean(loading)}><UploadCloud size={24}/><b>Upload from device</b><span>PDF / JPG / PNG</span></button><button type="button" className="source-choice" onClick={() => setCameraOpen(true)} disabled={Boolean(loading)}><Camera size={24}/><b>Take a photo</b><span>Use device camera</span></button><input ref={inputRef} onChange={pick} type="file" accept="image/jpeg,image/png,.pdf" hidden/></div>{file && <div className="upload-preview"><div className="upload-preview-media">{previewUrl ? <img src={previewUrl} alt="Selected document preview"/> : <FileText size={42}/>}</div><div><div className="eyebrow">{file.name.startsWith('bhumiai-capture-') ? 'CAMERA PHOTO' : 'SELECTED FILE'}</div><b>{file.name}</b><small>{file.type || 'Document'} · {(file.size / 1024 / 1024).toFixed(2)} MB</small></div><button className="button secondary" type="button" onClick={replaceFile} disabled={Boolean(loading)}><X size={15}/> Replace</button></div>}</section>
      <section className="card upload-card"><div className="section-head"><div><div className="eyebrow">RECORD DETAILS</div><h3>Document information</h3><p>Enter the source location and document type for this walk-in record.</p></div></div><form id="officer-upload-form" className="form-grid"><div className="field"><label>State</label><input name="state" required/></div><div className="field"><label>District</label><input name="district" required/></div><div className="field"><label>Tehsil</label><input name="tehsil" required/></div><div className="field"><label>Village</label><input name="village" required/></div><div className="field full"><label>Document Type</label><select name="document_type" required><option value="">Select type</option>{['Khatauni', 'Khasra', 'Jamabandi', 'Record of Rights', 'Registry', 'Other'].map(type => <option key={type}>{type}</option>)}</select></div></form></section>
    </div>
    <section className="card submission-actions-card officer-upload-actions"><div className="section-head"><div><h3>Ready for officer review</h3><p>Upload Record enters the standard preprocessing, exact-duplicate review, OCR, and verification workflow.</p></div><div className="actions"><Button onClick={upload} loading={loading === 'upload'} loadingText="Opening review…" disabled={!file || Boolean(loading)}><UploadCloud size={15}/> Upload Record</Button></div></div></section>
      {cameraOpen && <CameraCapture onUse={selectFile} onClose={() => setCameraOpen(false)}/>}
  </>;
}
