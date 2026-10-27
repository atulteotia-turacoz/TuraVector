/**
 * Manager Dashboard.
 * Order follows the dashboard pattern: KPI bar → activity → what needs attention → full list.
 * Colour is reserved for document status; everything else stays neutral.
 */
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, BarChart3, ChevronRight, FilePlus2, GitBranchPlus, Search, Upload, X } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { ErrorNotice, Loading, PageHeader, Pagination } from '@/components/ui';
import { formatDate, initials, timeAgo } from '@/lib/format';
import { usePageData } from '../shared';
import { PointsOfContact } from '@/features/organisation/PointsOfContact';
import { InvoicesDue } from '@/features/billing/InvoicesDue';
import { ApprovalsDue } from '@/features/billing/ApprovalsDue';
import { OrgFinancePanel } from '@/features/billing/OrgFinancePanel';
import { OurRateCard } from '@/features/organisation/OurRateCard';

interface DashboardData {
  total_documents: number; total_users: number; pending_reviews: number;
  draft_documents: number; under_review_documents: number; approved_documents: number; revision_documents: number;
  search_query: string;
  recent_documents: {
    items: { id: number; document_number: string; document_name: string; user_name: string; latest_version_status: number; created_at: string }[];
    page: number; pages: number; total: number;
  };
}
interface Insights {
  recent_uploads: { version_id: number; document_id: number; document_name: string; document_number: string; version_number: string;
    is_new_document: boolean; file_extension: string; uploaded_by: string; uploaded_at: string; stage_status: number }[];
  activity: { month: string; new_documents: number; new_versions: number }[];
  waiting: { assignment_id: number; document_id: number; document_name: string; version_number: string; reviewer: string;
    assigned_at: string; due_at: string; days_waiting: number; overdue: boolean; started: boolean }[];
  workload: { reviewer_id: number; reviewer: string; open: number; overdue: number; started: number; completed_30d: number }[];
  turnaround: { completed_90d: number; avg_days: number | null; on_time_pct: number | null; open: number; open_avg_age_days: number | null };
  top_contributors: { user_id: number; name: string; documents: number }[];
  new_documents_this_month: number; new_documents_last_month: number;
}

/** The dashboard search already understands status words (draft / review / approved / revision). */
const STAGES = [
  { status: 0, key: 'draft', label: 'Draft', color: 'var(--ink-3)' },
  { status: 1, key: 'review', label: 'Under review', color: 'var(--warn)' },
  { status: 3, key: 'revision', label: 'Needs revision', color: 'var(--danger)' },
  { status: 2, key: 'approved', label: 'Approved', color: 'var(--ok)' },
] as const;
const stageOf = (s: number) => STAGES.find((x) => x.status === s);
const monthLabel = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleString('en-US', { month: 'short' });

/** Where active documents are in the workflow — one bar per stage (one hue; the label carries identity). */
function DocumentPipeline({ counts, total }: { counts: Record<number, number>; total: number }) {
  const max = Math.max(1, ...STAGES.map((st) => counts[st.status] ?? 0));
  return (
    <section className="panel">
      <div className="panel-head"><div><h2>Document pipeline</h2><div className="small muted">Where your {total} documents are now</div></div></div>
      <ul className="md-hbars">
        {STAGES.map((st) => {
          const n = counts[st.status] ?? 0;
          const share = total ? Math.round((n / total) * 100) : 0;
          return (
            <li key={st.key} title={`${st.label}: ${n} document${n === 1 ? '' : 's'} (${share}%)`}>
              <span className="md-hbar-label">{st.label}</span>
              <span className="md-hbar-track"><span className="md-hbar-fill" style={{ width: `${(n / max) * 100}%` }} /></span>
              <span className="md-hbar-value tnum"><strong>{n}</strong> <span className="faint">{share}%</span></span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** How quickly reviews come back — headline numbers, not a chart. */
function ReviewTurnaround({ t }: { t: Insights['turnaround'] }) {
  return (
    <section className="panel">
      <div className="panel-head"><div><h2>Review turnaround</h2><div className="small muted">Reviews of your documents</div></div></div>
      <div className="md-tiles">
        <div><div className="stat-value tnum">{t.avg_days ?? '—'}{t.avg_days !== null && <span className="md-unit"> days</span>}</div>
          <div className="stat-label">Average time to review</div>
          <div className="stat-note">{t.completed_90d ? `${t.completed_90d} completed in 90 days` : 'None completed in 90 days'}</div></div>
        <div><div className="stat-value tnum">{t.on_time_pct ?? '—'}{t.on_time_pct !== null && '%'}</div>
          <div className="stat-label">Finished on time</div>
          <div className="stat-note">By the review date</div></div>
        <div><div className="stat-value tnum">{t.open}</div>
          <div className="stat-label">Open reviews</div>
          <div className="stat-note">{t.open_avg_age_days !== null ? `Waiting ${t.open_avg_age_days} days on average` : 'Nothing waiting'}</div></div>
      </div>
    </section>
  );
}

/** Who uploads most — top five over the last 12 months. */
function TopContributors({ rows }: { rows: Insights['top_contributors'] }) {
  const max = Math.max(1, ...rows.map((r) => r.documents));
  return (
    <section className="panel">
      <div className="panel-head"><div><h2>Top contributors</h2><div className="small muted">New documents in the last 12 months</div></div></div>
      {rows.length === 0 ? <div className="empty small">No uploads in the last 12 months.</div> : (
        <ul className="md-hbars">
          {rows.map((r) => (
            <li key={r.user_id} title={`${r.name}: ${r.documents} new document${r.documents === 1 ? '' : 's'}`}>
              <span className="md-hbar-label truncate">{r.name}</span>
              <span className="md-hbar-track"><span className="md-hbar-fill" style={{ width: `${(r.documents / max) * 100}%` }} /></span>
              <span className="md-hbar-value tnum"><strong>{r.documents}</strong></span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StatusText({ status }: { status: number }) {
  const st = stageOf(status);
  if (!st) return null;
  return <span className="md-status" style={{ color: st.color }}><span className="md-swatch" style={{ background: st.color }} />{st.label}</span>;
}

function ActivityChart({ data }: { data: Insights['activity'] }) {
  const max = Math.max(1, ...data.map((d) => d.new_documents + d.new_versions));
  return (
    <div className="md-chart" role="img" aria-label="Uploads per month for the last 12 months">
      {data.map((d, i) => {
        const total = d.new_documents + d.new_versions;
        return (
          <div key={d.month} className={`md-chart-col ${i === data.length - 1 ? 'is-current' : ''}`}
            title={`${monthLabel(d.month)}: ${d.new_documents} new documents, ${d.new_versions} new versions`}>
            <span className="md-chart-value tnum">{total || ''}</span>
            <div className="md-chart-track">
              <div className="md-chart-stack" style={{ height: `${(total / max) * 100}%` }}>
                {d.new_versions > 0 && <span className="md-chart-versions" style={{ flexGrow: d.new_versions }} />}
                {d.new_documents > 0 && <span className="md-chart-docs" style={{ flexGrow: d.new_documents }} />}
              </div>
            </div>
            <span className="md-chart-label">{monthLabel(d.month)}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function ManagerDashboard() {
  const { user } = useAuth();
  const showWorkload = !user?.is_org_admin;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const page = params.get('page') || '';
  const activeTab = STAGES.find((s) => s.key === search.trim().toLowerCase())?.key ?? (search ? 'search' : 'all');
  const [input, setInput] = useState(activeTab === 'search' ? search : '');
  const q = usePageData<DashboardData>(['manager-dashboard', search, page], '/api/users/manager-dashboard', { search, page: page || undefined });
  const ins = useQuery({
    queryKey: ['manager-dashboard', 'insights'],
    queryFn: async () => (await api.get<Insights>('/api/users/manager-dashboard/insights')).data,
  });

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;
  const i = ins.data;
  const total = d.total_documents;
  const counts: Record<number, number> = { 0: d.draft_documents, 1: d.under_review_documents, 2: d.approved_documents, 3: d.revision_documents };
  const pct = (n: number) => (total ? Math.round((n / total) * 100) : 0);
  const overdue = i?.workload.reduce((s, w) => s + w.overdue, 0) ?? 0;
  const yearUploads = i?.activity.reduce((s, a) => s + a.new_documents + a.new_versions, 0) ?? 0;

  const go = (next: Record<string, string>) => {
    const p = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => v && p.set(k, v));
    setParams(p);
  };
  const tab = (key: string) => { setInput(''); go(key === 'all' ? {} : { search: key }); };

  return (
    <div className="md">
      <PageHeader eyebrow="Content Review" title="Dashboard" subtitle="Every document across your team, and what is waiting on you."
        actions={<>
          <Link className="btn btn-secondary" to="/content-lab-management/reports/"><BarChart3 size={14} /> Reports</Link>
          <Link className="btn btn-primary" to="/content-lab-management/upload/"><Upload size={14} /> Upload document</Link>
        </>} />
      <ApprovalsDue />

      {/* KPI bar */}
      <div className="stat-grid md-kpis">
        <div className="stat"><div className="stat-value tnum">{total}</div><div className="stat-label">Documents</div>
          <div className="stat-note">{i ? `${i.new_documents_this_month} new this month · ${i.new_documents_last_month} last month` : 'All active documents'}</div></div>
        <div className="stat"><div className="stat-value tnum">{d.under_review_documents}</div><div className="stat-label">Under review</div><div className="stat-note">With a reviewer now</div></div>
        <div className="stat"><div className="stat-value tnum">{d.revision_documents}</div><div className="stat-label">Needs revision</div><div className="stat-note">Sent back to the author</div></div>
        <div className="stat"><div className="stat-value tnum">{d.pending_reviews}</div><div className="stat-label">Pending reviews</div>
          <div className="stat-note">{overdue > 0 ? <span style={{ color: 'var(--danger)' }}>{overdue} past due date</span> : 'Review assignments not finished'}</div></div>
        <div className="stat"><div className="stat-value tnum">{pct(d.approved_documents)}%</div><div className="stat-label">Approved</div><div className="stat-note">{d.approved_documents} of {total} documents</div></div>
      </div>

      {/* Activity + recent uploads */}
      <div className="md-row md-top">
        <div className="md-main">
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Upload activity</h2>
                <div className="small muted">{yearUploads} uploads in the last 12 months</div>
              </div>
              <div className="md-chart-key small muted">
                <span><span className="md-swatch" style={{ background: 'var(--accent)' }} /> New documents</span>
                <span><span className="md-swatch" style={{ background: 'var(--hairline-strong)' }} /> New versions</span>
              </div>
            </div>
            <div className="panel-body">{i ? <ActivityChart data={i.activity} /> : <Loading />}</div>
          </section>
          <DocumentPipeline counts={counts} total={total} />
          {i && <ReviewTurnaround t={i.turnaround} />}
          {i && <TopContributors rows={i.top_contributors} />}
          <OrgFinancePanel />
          <OurRateCard />
        </div>

        {/* right column: who to contact (university / organisation admins), then recent uploads */}
        <div className="md-side">
          <InvoicesDue />
          <PointsOfContact />
          <section className="panel md-feed">
            <div className="panel-head">
              <h2>Recent uploads</h2>
              <Link className="act" to="/content-lab-management/library/">View all</Link>
            </div>
            {!i ? <Loading /> : i.recent_uploads.length === 0 ? <div className="empty small">No uploads yet.</div> : (
              <ul className="md-feed-list">
                {i.recent_uploads.map((u) => (
                  <li key={u.version_id}>
                    <Link to={`/content-lab-management/document/${u.document_id}/`}>
                      <span className="md-feed-icon" title={u.is_new_document ? 'New document' : 'New version'}>
                        {u.is_new_document ? <FilePlus2 size={15} /> : <GitBranchPlus size={15} />}
                      </span>
                      <span className="grow" style={{ minWidth: 0 }}>
                        <span className="md-feed-title truncate" title={u.document_name}>{u.document_name}</span>
                        <span className="md-feed-meta">
                          {u.is_new_document ? 'New document' : `New version ${u.version_number.replace(`${u.document_number}-`, '')}`}
                          {' · '}{u.uploaded_by}{' · '}{timeAgo(u.uploaded_at)}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>

      {/* Needs attention (a workspace admin follows reviewers on the University page's Reviewers tab instead) */}
      <div className={`md-row ${showWorkload ? '' : 'single'}`}>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Waiting longest in review</h2>
              <div className="small muted">Open review assignments, oldest first</div>
            </div>
            <Link className="act" to="/content-lab-management/reviewer-assignments/">All assignments</Link>
          </div>
          {!i ? <Loading /> : i.waiting.length === 0 ? <div className="empty small">Nothing is waiting for review.</div> : (
            <div className="table-scroll">
              <table className="tbl tbl-clickable md-table">
                <thead><tr><th>Document</th><th>Reviewer</th><th className="right">Waiting</th><th className="right">Due</th></tr></thead>
                <tbody>
                  {i.waiting.map((w) => (
                    <tr key={w.assignment_id} onClick={() => navigate(`/content-lab-management/document/${w.document_id}/`)}>
                      <td className="md-doc">
                        <span className="md-doc-name" title={w.document_name}>{w.document_name}</span>
                        <span className="md-doc-number mono">{w.version_number}</span>
                      </td>
                      <td className="md-owner">{w.reviewer}<span className="md-sub">{w.started ? 'Review started' : 'Not started yet'}</span></td>
                      <td className="right nowrap tnum"><strong>{w.days_waiting}</strong> <span className="muted small">days</span></td>
                      <td className="right nowrap">
                        <span className="small">{formatDate(w.due_at)}</span>
                        {w.overdue && <span className="md-sub md-overdue"><AlertTriangle size={11} /> Overdue</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {showWorkload && (
          <section className="panel">
            <div className="panel-head">
              <h2>Reviewer workload</h2>
            </div>
            {!i ? <Loading /> : i.workload.length === 0 ? <div className="empty small">No open review assignments.</div> : (
              <ul className="md-load">
                {i.workload.map((w) => {
                  const maxOpen = Math.max(...i.workload.map((x) => x.open));
                  return (
                    <li key={w.reviewer_id}>
                      <span className="avatar">{initials(w.reviewer)}</span>
                      <span className="grow" style={{ minWidth: 0 }}>
                        <span className="between">
                          <span className="truncate small" style={{ fontWeight: 500 }}>{w.reviewer}</span>
                          <span className="small tnum"><strong>{w.open}</strong> open</span>
                        </span>
                        <span className="md-load-bar"><span style={{ width: `${(w.open / maxOpen) * 100}%` }} /></span>
                        <span className="md-sub">
                          {w.overdue > 0 && <span style={{ color: 'var(--danger)' }}>{w.overdue} overdue · </span>}
                          {w.started} started · {w.completed_30d} completed in 30 days
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        )}
      </div>

      {/* All documents */}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>All documents</h2>
            <div className="md-pipeline-legend">
              {STAGES.map((s) => (
                <button key={s.key} type="button" className={`md-legend-item ${activeTab === s.key ? 'is-active' : ''}`} onClick={() => tab(s.key)}>
                  <span className="md-swatch" style={{ background: s.color }} />
                  <span>{s.label}</span>
                  <strong className="tnum">{counts[s.status]}</strong>
                  <span className="faint tnum">{pct(counts[s.status])}%</span>
                </button>
              ))}
            </div>
          </div>
          <Link className="btn btn-secondary btn-sm" to="/content-lab-management/library/">View all in Library <ArrowRight size={13} /></Link>
        </div>
        <div className="md-pipeline-bar" aria-hidden>
          {STAGES.map((s) => counts[s.status] > 0 && (
            <button key={s.key} type="button" tabIndex={-1} onClick={() => tab(s.key)} title={`${s.label}: ${counts[s.status]}`}
              className={activeTab === s.key ? 'is-active' : ''} style={{ flexGrow: counts[s.status], background: s.color }} />
          ))}
        </div>

        <div className="md-toolbar">
          <div className="filter-tabs" role="tablist" aria-label="Filter by status">
            <button role="tab" aria-selected={activeTab === 'all'} className={`filter-tab ${activeTab === 'all' ? 'active' : ''}`} onClick={() => tab('all')}>All</button>
            {STAGES.map((s) => (
              <button key={s.key} role="tab" aria-selected={activeTab === s.key} className={`filter-tab ${activeTab === s.key ? 'active' : ''}`} onClick={() => tab(s.key)}>
                {s.label} <span className="md-tab-count tnum">{counts[s.status]}</span>
              </button>
            ))}
          </div>
          <form className="md-search" onSubmit={(e) => { e.preventDefault(); go({ search: input.trim() }); }}>
            <div className="search-input">
              <Search size={14} />
              <input className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Search number, name, owner…" aria-label="Search documents" />
            </div>
            {activeTab === 'search' && <button type="button" className="btn btn-ghost btn-sm" onClick={() => tab('all')}><X size={13} /> Clear</button>}
          </form>
        </div>

        {activeTab === 'search' && (
          <div className="md-result-note small muted">{d.recent_documents.total} result{d.recent_documents.total === 1 ? '' : 's'} for “{search}”</div>
        )}

        {d.recent_documents.items.length ? (
          <div className="table-scroll">
            <table className="tbl tbl-clickable md-table">
              <thead><tr><th>Document</th><th>Owner</th><th>Status</th><th className="right">Uploaded</th><th aria-label="Open" /></tr></thead>
              <tbody>
                {d.recent_documents.items.map((doc) => {
                  const open = () => navigate(`/content-lab-management/document/${doc.id}/`);
                  const ago = timeAgo(doc.created_at);
                  return (
                    <tr key={doc.id} onClick={open} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && open()}>
                      <td className="md-doc">
                        <span className="md-doc-name" title={doc.document_name}>{doc.document_name}</span>
                        <span className="md-doc-number mono">{doc.document_number}</span>
                      </td>
                      <td className="md-owner">{doc.user_name}</td>
                      <td className="nowrap"><StatusText status={doc.latest_version_status} /></td>
                      <td className="right nowrap">
                        <span className="small">{formatDate(doc.created_at)}</span>
                        {ago !== formatDate(doc.created_at) && <span className="md-sub">{ago}</span>}
                      </td>
                      <td className="md-chevron"><ChevronRight size={16} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty"><h3>No documents found</h3><p>Try another status or a different search.</p></div>
        )}

        {d.recent_documents.pages > 1 && (
          <Pagination page={d.recent_documents.page} pages={d.recent_documents.pages} total={d.recent_documents.total}
            onChange={(p) => go({ page: String(p), search })} />
        )}
      </section>
    </div>
  );
}
