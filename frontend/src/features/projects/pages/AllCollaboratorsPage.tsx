/** templates/projects/all_collaborators_projects.html */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Calendar, Eye, Filter, Folder, FolderKanban, Mail, Play, X } from 'lucide-react';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Empty, ErrorNotice, Loading, PageHeader, Stat } from '@/components/ui';
import { Avatar, fmtDay, StatusBadge, type Choice, type UserBrief } from '../shared';

interface Resp {
  collaborators_data: {
    user: UserBrief;
    projects: { project: { id: number; title: string; start_date: string | null }; role: string; role_display: string; joined_at: string }[];
  }[];
  all_projects: { value: number; label: string }[]; role_choices: Choice[];
  total_collaborators: number; total_collaborations: number;
}

const truncChars = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export default function AllCollaboratorsPage() {
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const role = params.get('role') || '';
  const project = params.get('project') || '';
  const [form, setForm] = useState({ search, role, project });
  useEffect(() => setForm({ search, role, project }), [search, role, project]);

  const q = useQuery({
    queryKey: ['projects', 'all-collaborators', search, role, project],
    queryFn: async () => (await api.get<Resp>('/api/projects/all-collaborators', { params: { search, role, project } })).data,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const p = new URLSearchParams();
    Object.entries(form).forEach(([k, v]) => { if (v) p.set(k, v); });
    setParams(p);
  };
  const filtered = !!(search || role || project);
  const d = q.data;

  return (
    <>
      <PageHeader title="All Project Collaborators" />
      <div className="stat-grid" style={{ marginBottom: 18 }}>
        <Stat value={d?.total_collaborators ?? '—'} label="Total Collaborators" />
        <Stat value={d?.total_collaborations ?? '—'} label="Project Assignments" />
      </div>

      <section className="panel" style={{ marginBottom: 18 }}>
        <form className="panel-body proj-filters" style={{ gridTemplateColumns: '2fr 1fr 1.5fr auto' }} onSubmit={submit}>
          <label className="field"><span className="field-label">Search</span>
            <input className="input" placeholder="Search collaborators or projects..." value={form.search} onChange={(e) => setForm({ ...form, search: e.target.value })} />
          </label>
          <label className="field"><span className="field-label">Role</span>
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="">All Roles</option>
              {d?.role_choices.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </label>
          <label className="field"><span className="field-label">Project</span>
            <select className="input" value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })}>
              <option value="">All Projects</option>
              {d?.all_projects.map((p) => <option key={p.value} value={String(p.value)}>{truncChars(p.label, 30)}</option>)}
            </select>
          </label>
          <button type="submit" className="btn btn-primary"><Filter size={14} /> Filter</button>
        </form>
      </section>

      {q.isLoading && <Loading />}
      {q.error && <ErrorNotice error={q.error} />}
      {d && (d.collaborators_data.length ? d.collaborators_data.map((c) => (
        <section key={c.user.id} className="panel proj-group">
          <div className="panel-head">
            <div className="row">
              <Avatar text={c.user.initials} />
              <div>
                <h2>{c.user.full_name}</h2>
                <div className="small muted row" style={{ gap: 14 }}>
                  <span className="row-tight"><Mail size={12} /> {c.user.email}</span>
                  <span className="row-tight"><FolderKanban size={12} /> {c.projects.length} project{c.projects.length === 1 ? '' : 's'}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="panel-body" style={{ paddingTop: 4, paddingBottom: 4 }}>
            {c.projects.map((p, i) => (
              <div key={`${p.project.id}-${i}`} className="proj-person">
                <Folder size={16} style={{ color: 'var(--ink-3)' }} />
                <div className="grow">
                  <div>{p.project.title}</div>
                  <div className="small muted row" style={{ gap: 14 }}>
                    <span className="row-tight"><Calendar size={12} /> Joined {formatDate(p.joined_at)}</span>
                    {p.project.start_date && <span className="row-tight"><Play size={12} /> Started {fmtDay(p.project.start_date)}</span>}
                  </div>
                </div>
                <StatusBadge value={p.role} label={p.role_display} />
                <Link to={`/journal-selector/projects/${p.project.id}/`} className="btn btn-secondary btn-sm"><Eye size={13} /> View</Link>
              </div>
            ))}
          </div>
        </section>
      )) : (
        <section className="panel">
          <Empty title="No Collaborators Found"
            action={filtered && <button className="btn btn-primary" onClick={() => setParams(new URLSearchParams())}><X size={14} /> Clear Filters</button>}>
            {filtered ? 'No collaborators match your current filters. Try adjusting your search criteria.' : 'No project collaborators found in the system yet.'}
          </Empty>
        </section>
      ))}
    </>
  );
}
