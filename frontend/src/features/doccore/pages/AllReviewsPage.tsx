/** all_reviews_view — documents/all_reviews.html */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Clock, Edit3, Eye, Filter, Inbox, RotateCcw, X } from 'lucide-react';
import { formatDate, initials } from '@/lib/format';
import { Badge, ErrorNotice, Field, Loading, PageHeader, Pagination, Panel, StageStatus } from '@/components/ui';
import { useDocPage, type UserBrief } from '../shared';
import type { Assignment } from './ReviewerDashboardPage';

interface Data {
  reviews: Assignment[]; total_reviews: number; status_filter: string; search_query: string; is_admin: boolean;
  page: number; num_pages: number; start_index: number; end_index: number;
}

function Person({ u }: { u: UserBrief }) {
  return (
    <span className="dc-person">
      <span className="dc-avatar">{`${u.first_name?.[0] ?? ''}${u.last_name?.[0] ?? ''}` || initials(u.username)}</span>
      <span>{u.full_name || u.username}</span>
    </span>
  );
}

const STATUS = {
  pending: { label: 'Pending', icon: <Clock size={12} />, tone: 'warn' as const },
  in_review: { label: 'In Review', icon: <Eye size={12} />, tone: 'accent' as const },
  completed: { label: 'Completed', icon: <CheckCircle2 size={12} />, tone: 'ok' as const },
  overdue: { label: 'Overdue', icon: <AlertTriangle size={12} />, tone: 'danger' as const },
};

export default function AllReviewsPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get('status') || 'all';
  const search = params.get('q') || '';
  const page = params.get('page') || undefined;
  const [form, setForm] = useState({ q: search, status });
  useEffect(() => setForm({ q: search, status }), [search, status]);
  const q = useDocPage<Data>(['all-reviews'], '/api/doccore/all-reviews', { status, q: search, page });
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setParams({ q: form.q, status: form.status });
  };
  const goPage = (p: number) => {
    const next: Record<string, string> = { page: String(p) };
    if (search) next.q = search;
    if (status !== 'all') next.status = status;
    setParams(next);
  };

  return (
    <div className="stack-lg">
      <PageHeader title="All Reviews"
        subtitle={d.is_admin ? 'Viewing all document reviews across the system' : 'Viewing your assigned document reviews'}
        actions={<Badge>Total: {d.total_reviews} Reviews</Badge>} />

      <Panel>
        <form className="form-grid" onSubmit={submit} style={{ gridTemplateColumns: 'minmax(0,2fr) minmax(0,1fr) auto auto auto', alignItems: 'end' }}>
          <Field label="Search">
            <input className="input" placeholder="Search by document name, number, or reviewer..." value={form.q}
              onChange={(e) => setForm({ ...form, q: e.target.value })} />
          </Field>
          <Field label="Status">
            <select className="input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
              <option value="all">All Status</option>
              <option value="pending">Pending</option>
              <option value="in_review">In Review</option>
              <option value="completed">Completed</option>
              <option value="overdue">Overdue</option>
            </select>
          </Field>
          <button type="submit" className="btn btn-primary"><Filter size={14} /> Filter</button>
          <Link to="/content-lab-management/all-reviews/" className="btn btn-secondary"><RotateCcw size={14} /> Reset</Link>
          <Link to="/content-lab-management/reviewer-dashboard/" className="btn btn-ghost btn-icon" title="Back to Dashboard"><ArrowLeft size={14} /></Link>
        </form>
      </Panel>

      <Panel flush>
        <div className="table-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Document</th><th>Version</th><th>Document Owner</th>{d.is_admin && <th>Reviewer</th>}
                <th>Review Due</th><th>Status</th>{d.is_admin && <th>Active</th>}<th>Created</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {d.reviews.length === 0 && (
                <tr><td colSpan={d.is_admin ? 9 : 7}>
                  <div className="empty"><Inbox size={32} className="faint" /><p className="muted">No reviews found matching your criteria.</p></div>
                </td></tr>
              )}
              {d.reviews.map((r) => {
                const s = STATUS[r.status];
                return (
                  <tr key={r.id}>
                    <td><strong>{r.document.document_name}</strong><span className="dc-sub">{r.document.document_number}</span></td>
                    <td><Badge>v{r.version.version_number}</Badge></td>
                    <td><Person u={r.document.owner} /></td>
                    {d.is_admin && <td><Person u={r.reviewer} /></td>}
                    <td>
                      {r.review_date ? <>{formatDate(r.review_date)}{r.is_overdue && <span className="dc-sub" style={{ color: 'var(--danger)' }}><AlertTriangle size={11} /> Overdue</span>}</>
                        : <span className="muted">Not set</span>}
                    </td>
                    <td>{s && <StageStatus label={s.label} tone={s.tone} />}</td>
                    {d.is_admin && <td>{r.is_active ? <Badge tone="ok"><Check size={11} /> Active</Badge> : <Badge><X size={11} /> Inactive</Badge>}</td>}
                    <td>{formatDate(r.created_at)}<span className="dc-sub">by {r.created_by.full_name || r.created_by.username}</span></td>
                    <td>
                      <span className="dc-btn-group">
                        <Link className="btn btn-secondary btn-sm btn-icon" title="View Document" to={`/content-lab-management/preview/${r.version.id}/`}><Eye size={14} /></Link>
                        {!r.is_completed && (
                          <Link className="btn btn-secondary btn-sm btn-icon" title="Review Document" to={`/content-lab-management/review/?id=${r.version.id}`}><Edit3 size={14} /></Link>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {d.num_pages > 1 && (
          <div style={{ padding: '0 16px 12px' }}>
            <div className="small muted" style={{ paddingTop: 12 }}>Showing {d.start_index} - {d.end_index} of {d.total_reviews} reviews</div>
            <Pagination page={d.page} pages={d.num_pages} onChange={goPage} />
          </div>
        )}
      </Panel>
    </div>
  );
}
