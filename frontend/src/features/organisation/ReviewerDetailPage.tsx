/** One reviewer of the admin's workspace documents: their numbers and every review of our documents. */
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, X } from 'lucide-react';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Badge, ErrorNotice, Loading, PageHeader, Pagination, Panel, Stat } from '@/components/ui';
import type { Reviewer, ReviewItem } from './OrganisationPage';
import './organisation.css';

const TONE: Record<ReviewItem['status'], 'ok' | 'danger' | 'warn' | undefined> = {
  completed: 'ok', overdue: 'danger', in_progress: 'warn', pending: undefined,
};
const PAGE = 20;

export default function ReviewerDetailPage() {
  const { userId } = useParams();
  const q = useQuery({
    queryKey: ['org', 'reviewer', userId],
    queryFn: async () => (await api.get(`/api/org/reviewers/${userId}`)).data as { reviewer: Reviewer; totals: Reviewer; items: ReviewItem[] },
  });
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const items = useMemo(() => (q.data?.items ?? []).filter((i) => !status || i.status === status), [q.data, status]);
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <ErrorNotice error={q.error} />;
  const { reviewer: r, totals: t } = q.data;
  const pages = Math.max(1, Math.ceil(items.length / PAGE));
  const current = Math.min(page, pages);

  return (
    <>
      <PageHeader eyebrow={<Link to="/content-lab-management/organisation/?tab=reviewers" className="row-tight"><ArrowLeft size={13} /> Reviewers</Link>}
        title={r.name}
        subtitle={<span className="row-tight wrap">
          {r.source === 'turacoz' ? <Badge tone="accent">Turacoz reviewer</Badge> : <Badge>Our member</Badge>}
          <Badge>{r.user_type_display}</Badge>
          <span className="small muted">{r.username} · {r.email}</span>
        </span>} />
      <div className="stat-grid org-stats">
        <Stat value={t.assigned} label="Reviews of our documents" />
        <Stat value={t.completed} label="Completed" note={t.assigned ? `${Math.round((t.completed / t.assigned) * 100)}% done` : undefined} />
        <Stat value={t.pending} label="Pending" note={`${t.in_progress} started`} />
        <Stat value={t.overdue} label="Overdue" note={t.overdue ? 'Past the review date' : 'None'} />
      </div>
      <Panel title={`Reviews (${items.length}${items.length !== q.data.items.length ? ` of ${q.data.items.length}` : ''})`} flush>
        <div className="org-poc-add">
          <select className="input" style={{ maxWidth: 220 }} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Status">
            <option value="">All statuses</option>
            <option value="pending">Pending</option><option value="in_progress">In progress</option>
            <option value="overdue">Overdue</option><option value="completed">Completed</option>
          </select>
          {status && <button className="btn btn-ghost btn-sm" onClick={() => { setStatus(''); setPage(1); }}><X size={13} /> Clear</button>}
        </div>
        {items.length === 0 ? <div className="panel-body muted small">No reviews match.</div> : (
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th>Document</th><th>Status</th><th>Assigned</th><th>Review date</th><th>Completed</th></tr></thead>
              <tbody>
                {items.slice((current - 1) * PAGE, current * PAGE).map((i) => (
                  <tr key={i.id}>
                    <td className="org-doc"><Link className="act" to={`/content-lab-management/document/${i.document_id}/`}>{i.document_name}</Link>
                      <div className="tiny faint mono">{i.version}</div></td>
                    <td><Badge tone={TONE[i.status]}>{i.status_label}</Badge></td>
                    <td className="nowrap small">{i.assigned_at ? formatDate(i.assigned_at) : '—'}</td>
                    <td className="nowrap small">{i.review_date ? formatDate(i.review_date) : '—'}</td>
                    <td className="nowrap small">{i.completed_at ? formatDate(i.completed_at) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && <div className="panel-body"><Pagination page={current} pages={pages} total={items.length} onChange={setPage} /></div>}
      </Panel>
    </>
  );
}
