'use client';

import {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import {Activity} from 'lucide-react';
import {api} from '../../../lib/api';
import {activityReference, actorLabel} from '../../../lib/activity';
import {Empty, ErrorMessage, Loader} from '../../../components/common/UI';

export default function SystemAudit() {
  const router = useRouter();
  const [developerMode, setDeveloperMode] = useState(null);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const enabled = window.localStorage.getItem('bhumiai-developer-mode') === 'on';
    setDeveloperMode(enabled);
    if (!enabled) router.replace('/officer');
  }, [router]);
  useEffect(() => {
    if (developerMode === true) api.audit().then(setRows).catch(loadError => setError(loadError.message));
  }, [developerMode]);

  if (developerMode === null) return null;
  if (!developerMode) return <section className="card"><div className="section-head"><div><div className="eyebrow">DEVELOPER MODE</div><h3>System Audit is hidden</h3><p>Enable Developer Mode to access System Audit.</p></div></div></section>;

  return <>
    <div className="page-title"><div><div className="eyebrow">DEVELOPER TOOLS</div><h2>System Audit</h2><p>Complete technical audit events for diagnostics and traceability.</p></div></div>
    <ErrorMessage>{error}</ErrorMessage>
    <section className="card activity-history-card system-audit-card">
      <div className="section-head"><div><div className="eyebrow">SYSTEM AUDIT</div><h3>Technical Events</h3><p>Complete raw audit data, including authentication, session, and system events.</p></div></div>
      {!rows ? <Loader label="Loading system audit…"/> : !rows.length ? <Empty title="No audit events recorded yet" text="Raw technical audit events will appear here."/> :
        <div className="table-wrap"><table className="data-table"><thead><tr><th>EVENT NAME</th><th>RECORD / SUBMISSION</th><th>ACTOR</th><th>ACCOUNT ID</th><th>WHEN</th><th>TECHNICAL DETAILS</th></tr></thead><tbody>{rows.map(event => <tr key={event.id}>
          <td>{event.action}</td>
          <td>{activityReference(event)}</td>
          <td>{actorLabel(event)}</td>
          <td>{event.user_id || '—'}</td>
          <td>{new Date(event.timestamp).toLocaleString()}</td>
          <td><code>{event.metadata_json || '—'}</code></td>
        </tr>)}</tbody></table></div>}
    </section>
    <p className="activity-footnote"><Activity size={14}/> Events remain traceable to their source record.</p>
  </>;
}
