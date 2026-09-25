'use client';

import {useEffect, useRef, useState} from 'react';
import {useRouter} from 'next/navigation';
import {Camera, CheckCircle2, FileText, Send, UploadCloud, X} from 'lucide-react';
import {request} from '../../../lib/api';
import CameraCapture from '../../../components/upload/CameraCapture';
import {Button, ErrorMessage, Toast} from '../../../components/common/UI';

function Journey({uploaded}) {
  return <ol className="citizen-journey" aria-label="Submission journey"><li className="current"><span>1</span><b>Select document</b></li><li className={uploaded ? 'complete' : ''}><span>{uploaded ? <CheckCircle2 size={14}/> : '2'}</span><b>Upload</b></li><li><span>3</span><b>Processing</b></li><li><span>4</span><b>Officer review</b></li><li><span>5</span><b>Verified record</b></li></ol>;
}

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [documentInfo, setDocumentInfo] = useState(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const inputRef = useRef(null);
  const formRef = useRef(null);
  const router = useRouter();
  const selectFile = nextFile => { setFile(nextFile || null); setDocumentInfo(null); setError(''); };
  const pick = event => selectFile(event.target.files?.[0]);
  const removeFile = () => { selectFile(null); if (inputRef.current) inputRef.current.value = ''; };

  useEffect(() => {
    if (!file?.type?.startsWith('image/')) { setPreviewUrl(''); return undefined; }
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  async function upload() {
    const form = formRef.current;
    if (!file || !form.reportValidity()) return;
    setLoading('upload'); setError('');
    try {
      const data = new FormData(form);
      data.append('file', file);
      setDocumentInfo(await request('/api/documents/upload', {method:'POST', body:data}));
      setFeedback({tone:'success', message:'Document uploaded. Submit it when you are ready for officer review.'});
    } catch { setError('We could not upload this document. Check the file and required location details, then try again.'); }
    finally { setLoading(''); }
  }

  async function submit() {
    if (!documentInfo) return;
    setLoading('submit'); setError('');
    try {
      await request(`/api/documents/${documentInfo.document_id}/submit`, {method:'POST'});
      router.push('/user/submissions?submitted=1');
    } catch { setError('We could not submit this document for review. Please try again.'); }
    finally { setLoading(''); }
  }

  return <>
    <div className="page-title citizen-page-title"><div><div className="eyebrow">NEW SUBMISSION</div><h2>Upload a land record</h2><p>Share a scanned, photographed, or camera-captured document for officer verification.</p></div></div>
    <Journey uploaded={Boolean(documentInfo)}/><ErrorMessage>{error}</ErrorMessage><Toast message={feedback?.message} tone={feedback?.tone} onDismiss={() => setFeedback(null)}/>
    <div className="split upload-layout citizen-upload-layout">
      <section className="card upload-card source-upload-card"><div className="section-head"><div><div className="eyebrow">STEP 1</div><h3>Upload document</h3><p>Choose a file or take a clear photo of the physical record.</p></div></div><div className="source-choice-grid"><button type="button" className="source-choice" onClick={() => inputRef.current?.click()} disabled={Boolean(loading)}><UploadCloud size={24}/><b>Upload from device</b><span>PDF / JPG / PNG</span></button><button type="button" className="source-choice" onClick={() => setCameraOpen(true)} disabled={Boolean(loading)}><Camera size={24}/><b>Take a photo</b><span>Use device camera</span></button><input ref={inputRef} onChange={pick} type="file" accept="image/jpeg,image/png,.pdf" hidden/></div>{file && <div className="upload-preview"><div className="upload-preview-media">{previewUrl ? <img src={previewUrl} alt="Selected document preview"/> : <FileText size={42}/>}</div><div><div className="eyebrow">{file.name.startsWith('bhumiai-capture-') ? 'CAMERA PHOTO' : 'SELECTED FILE'}</div><b>{file.name}</b><small>{file.type || 'Document'} · {(file.size / 1024 / 1024).toFixed(2)} MB</small></div><button className="button secondary" type="button" onClick={removeFile} disabled={Boolean(loading)}><X size={15}/> Replace</button></div>}</section>
      <section className="card upload-card citizen-metadata-card"><div className="section-head"><div><div className="eyebrow">STEP 2</div><h3>Document location</h3><p>These details help identify the record during review.</p></div></div><form ref={formRef} id="meta-form" className="form-grid"><div className="field"><label>State</label><input name="state" required/></div><div className="field"><label>District</label><input name="district" required/></div><div className="field"><label>Tehsil</label><input name="tehsil" required/></div><div className="field"><label>Village</label><input name="village" required/></div><div className="field full"><label>Document type</label><select name="document_type" required><option value="">Select type</option>{['Khatauni','Khasra','Jamabandi','Record of Rights','Registry','Other'].map(type => <option key={type}>{type}</option>)}</select></div></form></section>
    </div>
    <section className="card submission-actions-card citizen-upload-actions"><div className="section-head"><div><div className="eyebrow">NEXT STEP</div><h3>Submit for verification</h3><p>{documentInfo ? 'Your document is uploaded. Send it to the officer review queue.' : 'Select a document and complete the location details to upload it.'}</p></div><div className="actions"><Button onClick={upload} loading={loading === 'upload'} loadingText="Uploading…" disabled={!file || Boolean(loading)}><UploadCloud size={15}/> Upload document</Button><Button onClick={submit} loading={loading === 'submit'} loadingText="Submitting…" disabled={!documentInfo || Boolean(loading)}><Send size={15}/> Submit for review</Button></div></div></section>
      {cameraOpen && <CameraCapture onUse={selectFile} onClose={() => setCameraOpen(false)}/>}
  </>;
}
