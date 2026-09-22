'use client';

import {useEffect, useState} from 'react';
import {Activity} from 'lucide-react';
import {api} from '../../../lib/api';
import {activityDescription, activityLabel, activityReference, actorLabel, isWorkLogEvent} from '../../../lib/activity';
import {Empty, ErrorMessage, Loader} from '../../../components/common/UI';

export default function WorkLog() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api.audit().then(setRows).catch(loadError => setError(loadError.message)); }, []);
  const workLogRows = rows?.filter(isWorkLogEvent) || [];

  return <>
    <div className="page-title"><div><div className="eyebrow">OFFICER WORKSPACE</div><h2>Work Log</h2><p>A readable timeline of land-record handling and verification work.</p></div></div>
    <ErrorMessage>{error}</ErrorMessage>
    <section className="card activity-history-card">
      {!rows ? <Loader label="Loading work log…"/> : !workLogRows.length ? <Empty title="No workflow activity recorded yet" text="Document uploads and review actions will appear here."/> :
        <div className="table-wrap"><table className="data-table"><thead><tr><th>ACTION</th><th>RECORD / SUBMISSION</th><th>ACTOR</th><th>WHEN</th></tr></thead><tbody>{workLogRows.map(event => <tr key={event.id}>
          <td><span className="activity-action">{activityLabel(event.action)}</span><div className="activity-description">{activityDescription(event)}</div></td>
          <td>{activityReference(event)}</td>
          <td>{actorLabel(event)}</td>
          <td>{new Date(event.timestamp).toLocaleString()}</td>
        </tr>)}</tbody></table></div>}
    </section>
    <section className="card activity-history-card system-audit-card developer-only">
      <div className="section-head"><div><div className="eyebrow">DEVELOPER MODE</div><h3>System Audit / Technical Events</h3><p>Complete raw audit data, including authentication, session, and system events.</p></div></div>
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
