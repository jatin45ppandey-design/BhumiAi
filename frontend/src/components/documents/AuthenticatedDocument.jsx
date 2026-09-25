'use client';

import {useEffect, useState} from 'react';
import {api} from '../../lib/api';

export default function AuthenticatedDocument({documentId, variant = 'original', isPdf = false, alt, title, style}) {
  const [source, setSource] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    let objectUrl = '';
    setSource('');
    setError('');
    setLoading(true);
    api.documentContent(documentId, variant).then(blob => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setSource(objectUrl);
    }).catch(loadError => {
      if (active) setError(loadError.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId, variant]);

  if (loading) return <div className="document-source-state" role="status">Loading source document…</div>;
  if (error) return <div className="document-source-state error" role="alert">{error}</div>;
  if (!source) return null;
  return isPdf
    ? <iframe src={source} title={title || alt || 'Land record document'} style={style}/>
    : <img src={source} alt={alt || 'Land record document'} style={style}/>;
}
