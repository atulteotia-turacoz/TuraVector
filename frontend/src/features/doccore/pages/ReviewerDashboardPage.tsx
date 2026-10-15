/**
 * reviewer_dashboard_view — documents/reviewer_dashboard.html (auto-refreshes every 5 minutes).
 *
 * Loads every active assignment once (status=all) and applies the tab filter client-side with the
 * same rules as the backend's _filter_status, so the "Up next", progress and per-reviewer panels can
 * use the full set without a second request.
 */
import { ApprovalsDue } from '@/features/billing/ApprovalsDue';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Clock, Eye, FileText, Info, List, Search } from 'lucide-react';
import { formatDate } from '@/lib/format';
import { Empty, ErrorNotice, Loading, PageHeader, Pagination, Spinner } from '@/components/ui';
import { RowMenu, stageLabel, useDocPage, useOffice365, type UserBrief } from '../shared';

export interface Assignment {
  id: number; status: 'completed' | 'overdue' | 'in_review' | 'pending'; is_overdue: boolean; is_completed: boolean;
  is_active: boolean; has_remarks: boolean; review_date: string | null; started_at: string | null; completed_at: string | null;
  created_at: string; reviewer: UserBrief; created_by: UserBrief;
  version: { id: number; version_number: string };
  document: { id: number; document_name: string; document_number: string; stage_status: number; document_type: string | null; owner: UserBrief };
}

interface Data {
  is_admin_view: boolean; user_full_name: string; current_filter: string;
  total_assignments: number; pending_reviews: number; completed_reviews: number; overdue_reviews: number; in_review_count: number;
  assigned_documents: Assignment[];
}

type Tab = 'all' | 'pending' | 'in_review' | 'overdue' | 'completed';

const EMPTY_TEXT: Record<string, string> = {
  all: "You don't have any document assignments yet.",
  pending: "You don't have any pending reviews.",
  in_review: 'Nothing is in review right now.',
  completed: "You haven't completed any reviews yet.",
  overdue: "You don't have any overdue reviews.",
};

/** Same rules as backend _filter_status. */
function matches(a: Assignment, tab: Tab): boolean {
  if (tab === 'pending') return !a.is_completed && !a.has_remarks;
  if (tab === 'in_review') return !a.is_completed && a.has_remarks;
  if (tab === 'completed') return a.is_completed;
  if (tab === 'overdue') return !a.is_completed && a.is_overdue;
  return true;
}

const REVIEW_STATE = {
  completed: { label: 'Completed', color: 'var(--ok)' },
  overdue: { label: 'Overdue', color: 'var(--danger)' },
  in_review: { label: 'In review', color: 'var(--accent)' },
  pending: { label: 'Pending', color: 'var(--warn)' },
} as const;
const DOC_STAGE_COLOR: Record<number, string> = { 0: 'var(--ink-3)', 1: 'var(--warn)', 2: 'var(--ok)', 3: 'var(--danger)' };

const DAY = 86_400_000;
function dueText(a: Assignment): { text: string; tone: 'danger' | 'warn' | 'muted' } | null {
  if (!a.review_date || a.is_completed) return null;
  const days = Math.round((new Date(a.review_date).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / DAY);
  if (days < 0) return { text: `${-days} day${days === -1 ? '' : 's'} overdue`, tone: 'danger' };
  if (days === 0) return { text: 'Due today', tone: 'warn' };
  if (days <= 3) return { text: `Due in ${days} day${days === 1 ? '' : 's'}`, tone: 'warn' };
  return { text: `Due in ${days} days`, tone: 'muted' };
}

function Dot({ color }: { color: string }) {
  return <span className="rd-dot" style={{ background: color }} />;
}

const PAGE = 15;

export default function ReviewerDashboardPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = ((params.get('status') || 'all') as Tab);
  const [term, setTerm] = useState('');
  const [page, setPage] = useState(1);
  const q = useDocPage<Data>(['reviewer-dashboard'], '/api/doccore/reviewer-dashboard', { status: 'all' }, { refetchInterval: 300000 });
  const o365 = useOffice365();
  const [loadingReview, setLoadingReview] = useState<number | null>(null);

  const all = q.data?.assigned_documents ?? [];
  const rows = useMemo(() => {
    const t = term.trim().toLowerCase();
    return all.filter((a) => matches(a, tab) && (!t || `${a.document.document_name} ${a.document.document_number} ${a.document.owner.full_name} ${a.reviewer.full_name}`.toLowerCase().includes(t)));
  }, [all, tab, term]);

  const insights = useMemo(() => {
    const open = all.filter((a) => !a.is_completed);
    const upNext = [...open].sort((x, y) => {
      if (x.is_overdue !== y.is_overdue) return x.is_overdue ? -1 : 1;
      return (x.review_date ?? '9999').localeCompare(y.review_date ?? '9999');
    }).slice(0, 5);
    const done = all.filter((a) => a.is_completed && a.completed_at);
    const turnaround = done.length
      ? Math.round(done.reduce((s, a) => s + (new Date(a.completed_at!).getTime() - new Date(a.created_at).getTime()), 0) / done.length / DAY)
      : null;
    const last30 = done.filter((a) => Date.now() - new Date(a.completed_at!).getTime() <= 30 * DAY).length;
    const byReviewer = new Map<string, { name: string; open: number; overdue: number; completed: number }>();
    all.forEach((a) => {
      const k = String(a.reviewer.id);
      const r = byReviewer.get(k) ?? { name: a.reviewer.full_name, open: 0, overdue: 0, completed: 0 };
      if (a.is_completed) r.completed += 1; else r.open += 1;
      if (!a.is_completed && a.is_overdue) r.overdue += 1;
      byReviewer.set(k, r);
    });
    return { upNext, turnaround, last30, reviewers: [...byReviewer.values()].sort((a, b) => b.open - a.open) };
  }, [all]);

  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const pct = d.total_assignments ? Math.round((d.completed_reviews / d.total_assignments) * 100) : 0;
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const visible = rows.slice((page - 1) * PAGE, page * PAGE);
  const setTab = (t: Tab) => { setPage(1); setParams(t === 'all' ? {} : { status: t }); };

  const reviewButton = (a: Assignment, small = true) => (
    <Link className={`btn btn-primary ${small ? 'btn-sm' : ''}`} to={`/content-lab-management/review/?id=${a.version.id}`}
      onClick={(e) => { e.stopPropagation(); setLoadingReview(a.id); }}>
      {loadingReview === a.id ? <Spinner label="Loading..." /> : <><Eye size={13} /> {a.started_at ? 'Continue review' : 'Start review'}</>}
    </Link>
  );

  const tabs: { value: Tab; label: string; count: number }[] = [
    { value: 'all', label: 'All', count: d.total_assignments },
    { value: 'pending', label: 'Pending', count: d.pending_reviews },
    { value: 'in_review', label: 'In review', count: d.in_review_count },
    { value: 'overdue', label: 'Overdue', count: d.overdue_reviews },
    { value: 'completed', label: 'Completed', count: d.completed_reviews },
  ];

  return (
    <div className="rd stack-lg">
      <PageHeader eyebrow="Reviewer Dashboard" title={`Welcome, ${d.user_full_name}`}
        subtitle={d.is_admin_view ? "All reviewers' document assignments" : 'Your document review assignments'}
        actions={<Link className="btn btn-secondary" to="/content-lab-management/all-reviews/"><List size={14} /> All reviews</Link>} />
      <ApprovalsDue />

      {/* KPIs */}
      <div className="stat-grid md-kpis">
        <div className="stat"><div className="stat-value tnum">{d.total_assignments}</div><div className="stat-label">Assigned</div><div className="stat-note">Active assignments</div></div>
        <div className="stat"><div className="stat-value tnum">{d.pending_reviews}</div><div className="stat-label">Pending</div><div className="stat-note">Not started yet</div></div>
        <div className="stat"><div className="stat-value tnum">{d.in_review_count}</div><div className="stat-label">In review</div><div className="stat-note">Remarks added, not submitted</div></div>
        <div className="stat"><div className="stat-value tnum" style={{ color: d.overdue_reviews ? 'var(--danger)' : undefined }}>{d.overdue_reviews}</div><div className="stat-label">Overdue</div><div className="stat-note">Past the due date</div></div>
        <div className="stat"><div className="stat-value tnum">{d.completed_reviews}</div><div className="stat-label">Completed</div><div className="stat-note">{pct}% of all assignments</div></div>
      </div>

      {/* Up next + progress */}
      <div className="md-row">
        <section className="panel">
          <div className="panel-head">
            <div><h2>Up next</h2><div className="small muted">Open reviews, overdue first, then by due date</div></div>
          </div>
          {insights.upNext.length === 0 ? (
            <div className="empty small"><CheckCircle2 size={22} style={{ color: 'var(--ok)' }} /><p>All caught up — nothing waiting for review.</p></div>
          ) : (
            <ul className="rd-next">
              {insights.upNext.map((a) => {
                const due = dueText(a);
                return (
                  <li key={a.id} onClick={() => navigate(`/content-lab-management/document/${a.document.id}/`)}>
                    <span className="grow" style={{ minWidth: 0 }}>
                      <span className="md-doc-name" title={a.document.document_name}>{a.document.document_name}</span>
                      <span className="md-sub">
                        <span className="mono">{a.document.document_number}</span> · {a.document.owner.full_name}
                        {d.is_admin_view && <> · reviewer {a.reviewer.full_name}</>}
                      </span>
                    </span>
                    {due && (
                      <span className={`rd-due rd-due-${due.tone}`}>
                        {due.tone === 'danger' ? <AlertTriangle size={12} /> : <Clock size={12} />} {due.text}
                      </span>
                    )}
                    {reviewButton(a)}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><h2>Review progress</h2></div>
          <div className="panel-body">
            <div className="md-rate">
              <span className="md-rate-value tnum">{pct}%</span>
              <span className="small muted">{d.completed_reviews} of {d.total_assignments} completed</span>
            </div>
            <div className="md-stack-bar" aria-hidden>
              {(['completed', 'in_review', 'pending', 'overdue'] as const).map((k) => {
                const n = k === 'completed' ? d.completed_reviews : k === 'in_review' ? d.in_review_count
                  : k === 'overdue' ? d.overdue_reviews : Math.max(0, d.pending_reviews - d.overdue_reviews);
                return n > 0 ? <span key={k} style={{ flexGrow: n, background: REVIEW_STATE[k].color }} title={`${REVIEW_STATE[k].label}: ${n}`} /> : null;
              })}
            </div>
            <dl className="rd-facts">
              <div><dt>Average turnaround</dt><dd className="tnum">{insights.turnaround !== null ? `${insights.turnaround} days` : '—'}</dd></div>
              <div><dt>Completed in last 30 days</dt><dd className="tnum">{insights.last30}</dd></div>
            </dl>
            {d.is_admin_view && insights.reviewers.length > 0 && (
              <>
                <div className="pop-head" style={{ padding: '18px 0 6px' }}>By reviewer</div>
                <ul className="rd-reviewers">
                  {insights.reviewers.slice(0, 6).map((r) => (
                    <li key={r.name}>
                      <span className="grow truncate">{r.name}</span>
                      <span className="small tnum"><strong>{r.open}</strong> open</span>
                      {r.overdue > 0 && <span className="small tnum" style={{ color: 'var(--danger)' }}>{r.overdue} overdue</span>}
                      <span className="small muted tnum">{r.completed} done</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </section>
      </div>

      {/* All assignments */}
      <section className="panel">
        <div className="md-toolbar">
          <div className="filter-tabs" role="tablist" aria-label="Review status">
            {tabs.map((t) => (
              <button key={t.value} role="tab" aria-selected={tab === t.value} className={`filter-tab ${tab === t.value ? 'active' : ''}`} onClick={() => setTab(t.value)}>
                {t.label} <span className="md-tab-count tnum">{t.count}</span>
              </button>
            ))}
          </div>
          <div className="search-input lib-search">
            <Search size={14} />
            <input className="input" value={term} onChange={(e) => { setTerm(e.target.value); setPage(1); }} placeholder="Document, number, owner…" aria-label="Search assignments" />
          </div>
        </div>

        {rows.length === 0 ? (
          <Empty title="No documents assigned">{term ? `Nothing matches “${term}”.` : EMPTY_TEXT[tab] ?? 'No documents match the current filter.'}</Empty>
        ) : (
          <div className="table-scroll">
            <table className="tbl tbl-clickable rd-table">
              <thead>
                <tr>
                  <th>Document</th>
                  {d.is_admin_view && <th>Reviewer</th>}
                  <th>Due</th>
                  <th>Review</th>
                  <th>Document status</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {visible.map((a) => {
                  const due = dueText(a);
                  const st = REVIEW_STATE[a.is_completed ? 'completed' : a.is_overdue ? 'overdue' : a.has_remarks ? 'in_review' : 'pending'];
                  return (
                    <tr key={a.id} className={a.is_overdue && !a.is_completed ? 'rd-overdue' : undefined} onClick={() => navigate(`/content-lab-management/document/${a.document.id}/`)}>
                      <td className="md-doc">
                        <span className="md-doc-name" title={a.document.document_name}>{a.document.document_name}</span>
                        <span className="md-sub"><span className="mono">{a.document.document_number}</span>{a.document.document_type ? ` · ${a.document.document_type}` : ''} · {a.document.owner.full_name}</span>
                      </td>
                      {d.is_admin_view && <td className="rd-reviewer-cell">{a.reviewer.full_name}</td>}
                      <td className="nowrap">
                        <span className="small">{a.review_date ? formatDate(a.review_date) : '—'}</span>
                        {a.is_completed && a.completed_at
                          ? <span className="md-sub" style={{ color: 'var(--ok)' }}>Submitted {formatDate(a.completed_at)}</span>
                          : due && <span className={`md-sub rd-due-${due.tone}`}>{due.text}</span>}
                      </td>
                      <td className="nowrap"><span className="rd-state" style={{ color: st.color }}><Dot color={st.color} />{st.label}</span></td>
                      <td className="nowrap"><span className="rd-state" style={{ color: DOC_STAGE_COLOR[a.document.stage_status] }}><Dot color={DOC_STAGE_COLOR[a.document.stage_status]} />{stageLabel(a.document.stage_status)}</span></td>
                      <td className="right nowrap" onClick={(e) => e.stopPropagation()}>
                        <span className="lib-actions">
                          {!a.is_completed && reviewButton(a)}
                          <RowMenu label={`More actions for ${a.document.document_number}`}>
                            {(close) => (
                              <>
                                <button className="pop-item" disabled={o365.busy === a.version.id} onClick={() => { close(); void o365.open(a.version.id); }}>
                                  {o365.busy === a.version.id ? <Spinner /> : <FileText size={14} />} Open in Office 365
                                </button>
                                <Link className="pop-item" to={`/content-lab-management/document/${a.document.id}/`} onClick={close}><Info size={14} /> Document details</Link>
                                <div className="pop-sep" />
                                <div className="pop-head">Assigned {formatDate(a.created_at)} by {a.created_by.full_name}</div>
                              </>
                            )}
                          </RowMenu>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && <Pagination page={page} pages={pages} total={rows.length} onChange={setPage} />}
      </section>
      {o365.popup}
    </div>
  );
}
