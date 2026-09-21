'use client';

import {useEffect, useState} from 'react';
import {Activity} from 'lucide-react';
import {api} from '../../../lib/api';
import {activityDescription, activityLabel, actorLabel} from '../../../lib/activity';
import {Empty, ErrorMessage, Loader} from '../../../components/common/UI';

export default function ActivityHistory() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api.audit().then(setRows).catch(loadError => setError(loadError.message)); }, []);

  return <>
    <div className="page-title"><div><div className="eyebrow">OFFICER WORKSPACE</div><h2>Activity History</h2><p>A readable timeline of document handling and verification actions.</p></div></div>
    <ErrorMessage>{error}</ErrorMessage>
    <section className="card">
      {!rows ? <Loader label="Loading recent activity…"/> : !rows.length ? <Empty title="No activity recorded yet" text="Document uploads and review actions will appear here."/> :
        <div className="table-wrap"><table className="data-table"><thead><tr><th>ACTIVITY</th><th>RECORD</th><th>ACTOR</th><th>WHEN</th><th className="developer-only">EVENT NAME</th><th className="developer-only">TECHNICAL DETAILS</th></tr></thead><tbody>{rows.map(event => <tr key={event.id}>
          <td><span className="activity-action">{activityLabel(event.action)}</span><div className="activity-description">{activityDescription(event)}</div></td>
          <td>{event.document_id ? `#${event.document_id}` : event.submission_id ? `Submission #${event.submission_id}` : '—'}</td>
          <td>{actorLabel(event)}</td>
          <td>{new Date(event.timestamp).toLocaleString()}</td>
          <td className="developer-only">{event.action}</td>
          <td className="developer-only"><code>{event.metadata_json || '—'}</code></td>
        </tr>)}</tbody></table></div>}
    </section>
    <p className="activity-footnote"><Activity size={14}/> Events remain traceable to their source record.</p>
  </>;
}
