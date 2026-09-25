'use client';

import {useEffect, useRef, useState} from 'react';
import {Camera, RefreshCw, X} from 'lucide-react';
import {Button} from '../common/UI';

const photoName = () => {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, '');
  return `bhumiai-capture-${stamp}.jpg`;
};

export default function CameraCapture({onUse, onClose}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const imageUrlRef = useRef('');
  const mountedRef = useRef(false);
  const [capturedFile, setCapturedFile] = useState(null);
  const [capturedUrl, setCapturedUrl] = useState('');
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(true);

  function stopCamera() {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  async function startCamera() {
    stopCamera();
    if (mountedRef.current) { setError(''); setStarting(true); }
    if (!navigator.mediaDevices?.getUserMedia) {
      if (mountedRef.current) {
        setError('Camera capture is not supported in this browser. Choose a file instead.');
        setStarting(false);
      }
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {facingMode: {ideal: 'environment'}, width: {ideal: 1920}, height: {ideal: 1080}},
        audio: false,
      });
      if (!mountedRef.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
    } catch (captureError) {
      if (!mountedRef.current) return;
      setError(captureError?.name === 'NotAllowedError'
        ? 'Camera permission was denied. Allow camera access or choose a file instead.'
        : 'We could not start the camera. Choose a file instead.');
    } finally { if (mountedRef.current) setStarting(false); }
  }

  useEffect(() => {
    mountedRef.current = true;
    startCamera();
    return () => {
      mountedRef.current = false;
      stopCamera();
      if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
    };
  }, []);

  function capturePhoto() {
    const video = videoRef.current;
    if (!video?.videoWidth || !video?.videoHeight) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => {
      if (!mountedRef.current) return;
      if (!blob) { setError('We could not capture that photo. Please try again.'); return; }
      const file = new File([blob], photoName(), {type: 'image/jpeg'});
      if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
      const url = URL.createObjectURL(file);
      imageUrlRef.current = url;
      setCapturedFile(file);
      setCapturedUrl(url);
      stopCamera();
    }, 'image/jpeg', .92);
  }

  function retake() {
    if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
    imageUrlRef.current = '';
    setCapturedUrl(''); setCapturedFile(null);
    startCamera();
  }

  function usePhoto() {
    if (!capturedFile) return;
    onUse(capturedFile);
    onClose();
  }

  return <div className="modal-backdrop camera-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="camera-capture-title">
    <div className="modal-card camera-capture-card">
      <div className="section-head"><div><div className="eyebrow">DEVICE CAMERA</div><h3 id="camera-capture-title">Take a document photo</h3><p>Frame the whole record clearly before capturing.</p></div><button className="camera-close" type="button" onClick={onClose} aria-label="Close camera"><X size={18}/></button></div>
      <div className="camera-stage">
        {capturedUrl ? <img src={capturedUrl} alt="Captured document"/> : <video ref={videoRef} autoPlay playsInline muted/>}
        {!capturedUrl && starting && <span className="camera-status">Starting camera…</span>}
        {error && <p className="camera-error">{error}</p>}
      </div>
      <div className="actions camera-actions">
        {capturedFile ? <><Button variant="secondary" onClick={retake}><RefreshCw size={15}/> Retake</Button><Button onClick={usePhoto}>Use Photo</Button></> : <><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={capturePhoto} disabled={Boolean(error) || starting}><Camera size={15}/> Capture Photo</Button></>}
      </div>
    </div>
  </div>;
}
