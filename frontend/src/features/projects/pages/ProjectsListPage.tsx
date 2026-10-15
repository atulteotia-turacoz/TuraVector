/** templates/projects/projects_list.html */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Calendar, Edit, Eye, Filter, FolderKanban, Plus, Trash2, User, Users, X } from 'lucide-react';
import { api } from '@/lib/api';
import { Empty, ErrorNotice, Loading, PageHeader, Pagination } from '@/components/ui';
import { fmtDay, StatusBadge, titleCase, type Choice, type ProjectSummary } from '../shared';

interface ListResponse {
  items: ProjectSummary[]; total: number; page: number; pages: number; start_index: number; end_index: number;
  search_query: string; status_filter: string; priority_filter: string; sort_by: string;
  status_choices: Choice[]; priority_choices: Choice[];
}

const SORTS: Choice[] = [
  { value: '-created_at', label: 'Newest First' }, { value: 'created_at', label: 'Oldest First' },
  { value: 'title', label: 'Title A-Z' }, { value: '-title', label: 'Title Z-A' },
  { value: 'deadline', label: 'Deadline Soon' }, { value: '-deadline', label: 'Deadline Later' },
];

export default function ProjectsListPage() {
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const status = params.get('status') || '';
  const priority = params.get('priority') || '';
  const sort = params.get('sort') || '-created_at';
  const page = params.get('page') || '';

  const [form, setForm] = useState({ search, status, priority, sort });
  useEffect(() => setForm({ search, status, priority, sort }), [search, status, priority, sort]);

  const q = useQuery({
    queryKey: ['projects', 'list', search, status, priority, sort, page],
    queryFn: async () => (await api.get<ListResponse>('/api/projects', { params: { search, status, priority, sort, page: page || undefined } })).data,
  });

  const go = (next: Record<string, string>) => {
    const p = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => { if (v) p.set(k, v); });
    setParams(p);
  };
  const submit = (e: FormEvent) => { e.preventDefault(); go(form); };
  const filtered = !!(search || status || priority);
  const d = q.data;

  return (
    <>
      <PageHeader title="My Projects" actions={<>
        <Link to="/journal-selector/collaborators/" className="btn btn-secondary"><Users size={15} /> Collaborators</Link>
        <Link to="/journal-selector/projects/create/" className="btn btn-primary"><Plus size={15} /> New Project</Link>
      </>} />

      <section className="panel">
        <div className="panel-body">
          <form className="proj-filters" onSubmit={submit}>
            <label className="field">
              <span className="field-label">Search Projects</span>
              <input className="input" placeholder="Search by title, description, keywords..." value={form.search}
                onChange={(e) => setForm({ ...form, search: e.target.value })} />
            </label>
            <label className="field">
              <span className="field-label">Status</span>
              <select className="input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                <option value="">All Status</option>
                {d?.status_choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Priority</span>
              <select className="input" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                <option value="">All Priorities</option>
                {d?.priority_choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Sort By</span>
              <select className="input" value={form.sort} onChange={(e) => setForm({ ...form, sort: e.target.value })}>
                {SORTS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </label>
            <button type="submit" className="btn btn-primary"><Filter size={14} /> Apply</button>
          </form>

          {filtered && (
            <div className="proj-chips">
              {search && <span className="badge proj-chip">Search: "{search}"
                <button type="button" aria-label="Remove search filter" onClick={() => go({ status, priority, sort })}><X size={12} /></button></span>}
              {status && <span className="badge proj-chip">Status: {titleCase(status)}
                <button type="button" aria-label="Remove status filter" onClick={() => go({ search, priority, sort })}><X size={12} /></button></span>}
              {priority && <span className="badge proj-chip">Priority: {titleCase(priority)}
                <button type="button" aria-label="Remove priority filter" onClick={() => go({ search, status, sort })}><X size={12} /></button></span>}
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setParams(new URLSearchParams())}><X size={13} /> Clear All</button>
            </div>
          )}
        </div>
      </section>

      <div style={{ marginTop: 20 }}>
        {q.isLoading && <Loading />}
        {q.error && <ErrorNotice error={q.error} />}
        {d && d.total > 0 && (
          <>
            <p className="small muted" style={{ marginBottom: 12 }}>
              Showing {d.start_index}-{d.end_index} of {d.total} projects{filtered ? ' (filtered)' : ''}
            </p>
            <div className="proj-cards">
              {d.items.map((p) => (
                <article key={p.id} className="proj-card">
                  <div className="proj-card-body">
                    <h3>{p.title}</h3>
                    <p className="muted small">{p.description_short}</p>
                    <div className="proj-meta">
                      <StatusBadge value={p.status} label={p.status_display} />
                      <span><User size={13} /> {p.owner.full_name}</span>
                      <span><Users size={13} /> {p.collaborator_count} collaborators</span>
                      {p.deadline && <span><Calendar size={13} /> {fmtDay(p.deadline)}</span>}
                    </div>
                  </div>
                  <div className="proj-card-foot">
                    <Link to={`/journal-selector/projects/${p.id}/`} className="btn btn-primary btn-sm"><Eye size={13} /> View</Link>
                    {p.is_owner && <>
                      <Link to={`/journal-selector/projects/${p.id}/edit/`} className="btn btn-secondary btn-sm"><Edit size={13} /> Edit</Link>
                      <Link to={`/journal-selector/projects/${p.id}/delete/`} className="btn btn-danger btn-sm"><Trash2 size={13} /> Delete</Link>
                    </>}
                  </div>
                </article>
              ))}
            </div>
            <div style={{ marginTop: 16 }}>
              <Pagination page={d.page} pages={d.pages} total={d.total}
                onChange={(n) => go({ search, status, priority, sort, page: String(n) })} />
            </div>
          </>
        )}
        {d && d.total === 0 && (
          <section className="panel">
            <Empty title="No Projects Yet" action={<Link to="/journal-selector/projects/create/" className="btn btn-primary"><Plus size={15} /> Create First Project</Link>}>
              <FolderKanban size={28} style={{ margin: '0 auto 10px', color: 'var(--ink-3)' }} />
              Create your first project to get started with collaborative research.
            </Empty>
          </section>
        )}
      </div>
    </>
  );
}
