/** reviewer_assignments_overview — documents/reviewer_assignments_overview.html */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AlertTriangle, Inbox, RotateCcw, Search, UserPlus, Users, UserX } from 'lucide-react';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Loading, PageHeader, Pagination, Stat } from '@/components/ui';
import { Stage, useDocPage, type UserBrief } from '../shared';

interface Row {
  document: { id: number; document_number: string; document_name: string; stage_status: number; owner: UserBrief; has_versions: boolean; has_approved_version: boolean };
  has_reviewers: boolean;
  active_reviewers: { id: number; reviewer: UserBrief; assigned_at: string | null; started_at: string | null }[];
  total_reviewers: number; completed_reviews: number;
}
interface Data {
  page_title: string; document_data: Row[]; filter_status: string; filter_document_status: string; search_query: string;
  total_documents: number; documents_with_reviewers: number; documents_without_reviewers: number; documents_needing_reviewers: number;
  stage_choices: { value: number; label: string }[];
}

/** Django |truncatechars:50 */
function truncatechars(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

const PAGE_SIZE = 25;

export default function ReviewerAssignmentsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const filter_status = params.get('filter_status') || 'all';
  const document_status = params.get('document_status') || 'all';
  const search = params.get('search') || '';
  const [input, setInput] = useState(search);
  const [page, setPage] = useState(1);
  useEffect(() => { setInput(search); setPage(1); }, [search, filter_status, document_status]);
  const q = useDocPage<Data>(['reviewer-assignments'], '/api/doccore/reviewer-assignments', { filter_status, document_status, search });
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  const update = (next: Partial<{ filter_status: string; document_status: string; search: string }>) => {
    const merged = { filter_status, document_status, search, ...next };
    const p = new URLSearchParams();
    Object.entries(merged).forEach(([k, v]) => { if (v && v !== 'all') p.set(k, v); });
    setParams(p);
  };
  const submit = (e: FormEvent) => { e.preventDefault(); update({ search: input.trim() }); };
  const pages = Math.max(1, Math.ceil(d.document_data.length / PAGE_SIZE));
  const rows = d.document_data.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const filtered = filter_status !== 'all' || document_status !== 'all' || !!search;

  return (
    <div className="stack-lg">
      <PageHeader title={d.page_title} subtitle="Which documents have reviewers, and which still need one." />

      <div className="stat-grid">
        <Stat value={d.total_documents} label="Documents" note="All active documents" />
        <Stat value={d.documents_with_reviewers} label="With reviewers" note="At least one active reviewer" />
        <Stat value={d.documents_without_reviewers} label="Without reviewers" note="No active reviewer yet" />
        <Stat value={<span style={{ color: d.documents_needing_reviewers ? 'var(--danger)' : undefined }}>{d.documents_needing_reviewers}</span>}
          label="Need reviewers" note="Under review but nobody assigned" />
      </div>

      <section className="panel">
        <div className="md-toolbar ra-toolbar">
          <div className="filter-tabs" role="tablist" aria-label="Reviewer status">
            {([['all', 'All'], ['assigned', 'With reviewers'], ['unassigned', 'Without reviewers']] as const).map(([v, label]) => (
              <button key={v} role="tab" aria-selected={filter_status === v} className={`filter-tab ${filter_status === v ? 'active' : ''}`}
                onClick={() => update({ filter_status: v })}>{label}</button>
            ))}
          </div>
          <div className="row ra-filters">
            <select className="input ra-select" aria-label="Document status" value={document_status} onChange={(e) => update({ document_status: e.target.value })}>
              <option value="all">All statuses</option>
              {d.stage_choices.map((c) => <option key={c.value} value={String(c.value)}>{c.label}</option>)}
            </select>
            <form className="search-input ra-search" onSubmit={submit}>
              <Search size={14} />
              <input className="input" placeholder="Name, number or owner…" value={input} onChange={(e) => setInput(e.target.value)} aria-label="Search" />
            </form>
            {filtered && <Link to="/content-lab-management/reviewer-assignments/" className="btn btn-ghost btn-sm"><RotateCcw size={13} /> Reset</Link>}
          </div>
        </div>

        {d.document_data.length === 0 ? (
          <div className="empty"><Inbox size={32} className="faint" /><p className="muted">No documents found matching your criteria.</p></div>
        ) : (
          <div className="table-scroll">
            <table className="tbl tbl-clickable ra-table">
              <thead>
                <tr><th>Document</th><th>Owner</th><th>Status</th><th>Reviewers</th><th className="right" aria-label="Actions" /></tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const attention = r.document.stage_status === 1 && !r.has_reviewers;
                  const open = () => navigate(`/content-lab-management/document/${r.document.id}/`);
                  const canAssign = r.document.has_versions && !r.document.has_approved_version;
                  return (
                    <tr key={r.document.id} className={attention ? 'ra-attention' : undefined} onClick={open}>
                      <td className="md-doc">
                        <span className="md-doc-name" title={r.document.document_name}>{truncatechars(r.document.document_name, 90)}</span>
                        <span className="md-doc-number mono">{r.document.document_number}</span>
                      </td>
                      <td className="ra-owner">
                        <span className="truncate" style={{ display: 'block' }}>{r.document.owner.full_name}</span>
                        <span className="md-sub truncate">{r.document.owner.email}</span>
                      </td>
                      <td className="nowrap"><Stage value={r.document.stage_status} /></td>
                      <td className="ra-reviewers">
                        {r.has_reviewers ? (
                          <>
                            {r.active_reviewers.map((a) => (
                              <span key={a.id} className="ra-reviewer" title={`Assigned ${a.assigned_at ? formatDate(a.assigned_at) : ''}${a.started_at ? ` · started ${formatDate(a.started_at)}` : ''}`}>
                                <span className={`ra-dot ${a.started_at ? 'is-started' : ''}`} />{a.reviewer.full_name}
                                <span className="md-sub" style={{ display: 'inline', marginLeft: 6 }}>{a.started_at ? 'started' : 'not started'}</span>
                              </span>
                            ))}
                            <span className="md-sub tnum">{r.completed_reviews} of {r.total_reviewers} review{r.total_reviewers === 1 ? '' : 's'} completed</span>
                          </>
                        ) : attention ? (
                          <span className="ra-missing"><AlertTriangle size={13} /> Needs a reviewer</span>
                        ) : (
                          <span className="faint small row-tight"><UserX size={13} /> Not assigned</span>
                        )}
                      </td>
                      <td className="right nowrap" onClick={(e) => e.stopPropagation()}>
                        <span className="ra-actions">
                          {canAssign && (
                            <Link className={`btn btn-sm ${attention ? 'btn-primary' : 'btn-secondary'}`} title="Assign Reviewer" to={`/content-lab-management/document/${r.document.id}/assign-reviewer/`}>
                              <UserPlus size={13} /><span className="ra-label">Assign</span>
                            </Link>
                          )}
                          {r.document.has_versions && (
                            <Link className="btn btn-secondary btn-sm" title="Manage Reviewers" to={`/content-lab-management/document/${r.document.id}/manage-reviewers/`}><Users size={13} /><span className="ra-label">Manage</span></Link>
                          )}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && <Pagination page={page} pages={pages} total={d.document_data.length} onChange={(p) => { setPage(p); window.scrollTo({ top: 0 }); }} />}
      </section>
    </div>
  );
}
