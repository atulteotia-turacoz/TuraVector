import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Eye, RotateCcw } from 'lucide-react';
import { api } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { ScopeBanner } from '@/components/Shell';
import { Empty, ErrorNotice, Field, Loading, PageHeader, Pagination, Panel, Spinner, Stat } from '@/components/ui';
import type { EmailLogRow, MailLogs } from './api';
import { StatusBadge, useRetryEmail } from './shared';
import './tools.css';

const FILTER_KEYS = ['email_type', 'status', 'search', 'date_from', 'date_to'] as const;

/** documents/mail_logs.html */
export default function MailLogsPage() {
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) || ''])) as Record<(typeof FILTER_KEYS)[number], string>;
  const page = params.get('page') || '';
  const [draft, setDraft] = useState(filters);
  useEffect(() => setDraft(filters), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps

  const q = useQuery({
    queryKey: ['tools', 'mail-logs', params.toString()],
    queryFn: async () => (await api.get<MailLogs>('/api/tools/mail-logs', { params: { ...filters, page: page || undefined } })).data,
  });
  const { retry, retrying } = useRetryEmail(() => q.refetch());

  // Auto-refresh every 30 seconds while there are pending emails
  const pending = q.data?.stats.pending ?? 0;
  useEffect(() => {
    if (pending <= 0) return;
    const t = setTimeout(() => q.refetch(), 30000);
    return () => clearTimeout(t);
  }, [pending, q.dataUpdatedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  const apply = (e: FormEvent) => {
    e.preventDefault();
    const p = new URLSearchParams();
    FILTER_KEYS.forEach((k) => draft[k] && p.set(k, draft[k]));
    setParams(p);
  };
  const gotoPage = (n: number) => { const p = new URLSearchParams(params); p.set('page', String(n)); setParams(p); };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  return (
    <div className="stack-lg">
      <PageHeader title="Email Logs" />
      <ScopeBanner scope="workspace" />
      <div className="grid-4">
        <Stat value={d.stats.total} label="Total Emails" />
        <Stat value={<span style={{ color: 'var(--ok)' }}>{d.stats.sent}</span>} label="Sent Successfully" />
        <Stat value={<span style={{ color: 'var(--danger)' }}>{d.stats.failed}</span>} label="Failed" />
        <Stat value={<span style={{ color: 'var(--warn)' }}>{d.stats.pending}</span>} label="Pending" />
      </div>

      <Panel title="Filters">
        <form className="tools-filters" onSubmit={apply}>
          <Field label="Email Type">
            <select className="input" value={draft.email_type} onChange={(e) => setDraft({ ...draft, email_type: e.target.value })}>
              <option value="">All Types</option>
              {d.email_types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
          <Field label="Status">
            <select className="input" value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
              <option value="">All Status</option>
              {d.status_choices.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
          <Field label="Search">
            <input className="input" placeholder="Email, subject, user..." value={draft.search}
              onChange={(e) => setDraft({ ...draft, search: e.target.value })} />
          </Field>
          <Field label="From Date">
            <input type="date" className="input" value={draft.date_from} onChange={(e) => setDraft({ ...draft, date_from: e.target.value })} />
          </Field>
          <Field label="To Date">
            <input type="date" className="input" value={draft.date_to} onChange={(e) => setDraft({ ...draft, date_to: e.target.value })} />
          </Field>
          <div className="row">
            <button type="submit" className="btn btn-primary btn-sm">Filter</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setParams(new URLSearchParams())}>Clear</button>
          </div>
        </form>
      </Panel>

      <Panel flush title="Email Logs" actions={<span className="badge">{d.total} total emails</span>}
        footer={d.pages > 1 ? <Pagination page={d.page} pages={d.pages} total={d.total} onChange={gotoPage} /> : undefined}>
        {d.items.length === 0 ? (
          <Empty title="No email logs found">Try adjusting your filters or check back later.</Empty>
        ) : (
          <div className="table-scroll">
            <table className="tbl">
              <thead>
                <tr><th>Type</th><th>Recipient</th><th>Subject</th><th>Status</th><th>Sent At</th><th>Created</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {d.items.map((e: EmailLogRow) => (
                  <tr key={e.id}>
                    <td><span className="badge badge-accent">{e.email_type_display}</span></td>
                    <td><strong>{e.recipient_email}</strong>{e.recipient_user && <div className="small muted">{e.recipient_user}</div>}</td>
                    <td>
                      <strong>{e.subject.length > 50 ? `${e.subject.slice(0, 49)}…` : e.subject}</strong>
                      {e.document && <div className="small muted">Doc: {e.document.document_number}</div>}
                    </td>
                    <td>
                      <StatusBadge status={e.status} display={e.status_display} />
                      {e.status === 'failed' && e.retry_count > 0 && <div className="small muted">Retries: {e.retry_count}</div>}
                    </td>
                    <td className="small nowrap">{e.sent_at ? formatDateTime(e.sent_at) : <span className="muted">-</span>}</td>
                    <td className="small nowrap">{formatDateTime(e.created_at)}</td>
                    <td>
                      <div className="actions">
                        <Link className="btn btn-ghost btn-icon" title="View details" to={`/documents/mail-logs/${e.id}/`}><Eye size={14} /></Link>
                        {e.status === 'failed' && e.retry_count < 3 && (
                          <button className="btn btn-ghost btn-sm" title="Retry" disabled={retrying === e.id} onClick={() => retry(e.id)}>
                            {retrying === e.id ? <><Spinner /> Retrying...</> : <RotateCcw size={14} />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
