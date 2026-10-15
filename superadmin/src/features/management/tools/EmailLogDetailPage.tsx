import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { ArrowLeft, RotateCcw } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { Loading, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import type { EmailLogRow } from './api';
import { StatusBadge, useRetryEmail } from './shared';
import './tools.css';

/** documents/email_log_detail.html */
export default function EmailLogDetailPage() {
  const { emailLogId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const q = useQuery({
    queryKey: ['tools', 'email-log', emailLogId],
    retry: false,
    queryFn: async () => (await api.get<{ email_log: EmailLogRow }>(`/api/tools/mail-logs/${emailLogId}`)).data.email_log,
  });
  // Django redirected back to the mail log list with an error message
  useEffect(() => {
    if (q.error) {
      const status = (q.error as any)?.response?.status;
      toast.error(status === 403 ? errorMessage(q.error) : `Error loading email details: ${errorMessage(q.error)}`);
      navigate('/documents/mail-logs/', { replace: true });
    }
  }, [q.error]); // eslint-disable-line react-hooks/exhaustive-deps
  const { retry, retrying } = useRetryEmail(() => q.refetch());

  if (q.isLoading || q.error) return <Loading />;
  const e = q.data!;

  return (
    <div className="stack-lg">
      <Link className="btn btn-ghost" to="/documents/mail-logs/"><ArrowLeft size={14} /> Back to Mail Logs</Link>
      <PageHeader title="Email Details" actions={<>
        <StatusBadge status={e.status} display={e.status_display} long />
        {e.status === 'failed' && e.retry_count < 3 && (
          <button className="btn btn-secondary btn-sm" disabled={retrying === e.id} onClick={() => retry(e.id)}>
            {retrying === e.id ? <><Spinner /> Retrying...</> : <><RotateCcw size={14} /> Retry</>}
          </button>
        )}
      </>} />

      <div className="grid-2">
        <Panel title="Email Information">
          <dl className="kv">
            <dt>Type:</dt><dd><span className="badge badge-accent">{e.email_type_display}</span></dd>
            <dt>Status:</dt><dd><StatusBadge status={e.status} display={e.status_display} /></dd>
            <dt>Recipient:</dt><dd><strong>{e.recipient_email}</strong>{e.recipient_user && <div className="small muted">{e.recipient_user}</div>}</dd>
            <dt>From:</dt><dd><strong>{e.from_email}</strong>{e.sender_user && <div className="small muted">{e.sender_user}</div>}</dd>
          </dl>
        </Panel>
        <Panel title="Timing & Status">
          <dl className="kv">
            <dt>Created:</dt><dd>{formatDateTime(e.created_at)}</dd>
            {e.sent_at && <><dt>Sent:</dt><dd>{formatDateTime(e.sent_at)}</dd></>}
            {e.retry_count > 0 && <><dt>Retry Count:</dt><dd><span className="badge badge-warn">{e.retry_count}</span></dd></>}
            {e.document && <>
              <dt>Document:</dt>
              <dd>
                <strong>{e.document.document_number}</strong>
                <div className="small muted">{e.document.document_name}</div>
                {e.document_version && <div className="small" style={{ color: 'var(--accent)' }}>Version: {e.document_version}</div>}
              </dd>
            </>}
          </dl>
        </Panel>
      </div>

      <Panel title="Subject"><div className="notice notice-accent">{e.subject}</div></Panel>
      <Panel title="Message Content"><div className="tools-email-body">{e.message_content}</div></Panel>
      {e.error_message && (
        <Panel title="Error Message"><div className="notice notice-danger"><pre className="tools-pre">{e.error_message}</pre></div></Panel>
      )}
    </div>
  );
}
