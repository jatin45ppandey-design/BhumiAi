'use client';

import {useRef, useState} from 'react';
import {ChevronDown, Download, FileJson, FileSpreadsheet, FileText} from 'lucide-react';
import {downloadAuthenticated} from '../../lib/download';

const formatDetails = {
  pdf: {label: 'PDF', icon: FileText},
  csv: {label: 'CSV', icon: FileSpreadsheet},
  json: {label: 'JSON', icon: FileJson},
};

function formatPath(scope, recordId, format) {
  const prefix = scope === 'officer' ? '/api/verified-records' : '/api/user/records';
  return `${prefix}/${encodeURIComponent(recordId)}/export/${format}`;
}

function fallbackFilename(recordId, format) {
  return `BhumiAI_Khatauni_${recordId}.${format}`;
}

function useExportDownload(scope, recordId, onFeedback) {
  const [activeFormat, setActiveFormat] = useState('');
  const inFlight = useRef(false);

  async function startDownload(format) {
    if (inFlight.current) return;
    inFlight.current = true;
    const detail = formatDetails[format];
    setActiveFormat(format);
    try {
      const result = await downloadAuthenticated(formatPath(scope, recordId, format), fallbackFilename(recordId, format));
      onFeedback?.({tone: 'success', message: `${detail.label} download started${result.filename ? `: ${result.filename}` : '.'}`});
      return true;
    } catch (error) {
      onFeedback?.({tone: 'error', message: error.message || 'Export failed. Please try again.'});
      return false;
    } finally {
      inFlight.current = false;
      setActiveFormat('');
    }
  }

  return {activeFormat, downloading: Boolean(activeFormat), startDownload};
}

function DownloadControl({scope, recordId, format, onFeedback, children, className = 'button'}) {
  const {activeFormat, downloading, startDownload} = useExportDownload(scope, recordId, onFeedback);
  const detail = formatDetails[format];

  return <button type="button" className={className} onClick={() => startDownload(format)} disabled={downloading} aria-busy={downloading}>
    {downloading && activeFormat === format ? `Preparing ${detail.label}...` : children}
  </button>;
}

export function OfficerExportMenu({recordId, onFeedback}) {
  const [open, setOpen] = useState(false);
  const {activeFormat, downloading, startDownload} = useExportDownload('officer', recordId, onFeedback);

  async function selectFormat(format) {
    const started = await startDownload(format);
    if (started) setOpen(false);
  }

  return <div className="export-menu">
    <button type="button" className="button secondary" onClick={() => setOpen(current => !current)} disabled={downloading} aria-busy={downloading} aria-expanded={open} aria-haspopup="menu">
      {downloading ? `Preparing ${formatDetails[activeFormat].label}...` : <><Download size={16}/> Export <ChevronDown size={15}/></>}
    </button>
    {open && <div className="export-menu-list" role="menu" aria-label="Export verified record">
      {Object.entries(formatDetails).map(([format, detail]) => {
        const Icon = detail.icon;
        return <button type="button" key={format} role="menuitem" disabled={downloading} onClick={() => selectFormat(format)}>
          <Icon size={16}/>{downloading && activeFormat === format ? `Preparing ${detail.label}...` : detail.label}
        </button>;
      })}
    </div>}
  </div>;
}

export function CitizenVerifiedDownload({recordId, onFeedback}) {
  return <DownloadControl scope="citizen" recordId={recordId} format="pdf" onFeedback={onFeedback} className="button secondary">
    <Download size={16}/> Download Verified Record
  </DownloadControl>;
}
