/** templates/projects/collaborators_list.html (collaborators_list_view + CollaboratorSearchForm) */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Edit, Eye, Search, Trash2, Users, X } from 'lucide-react';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Empty, ErrorNotice, Loading, PageHeader } from '@/components/ui';
import { Avatar, StatusBadge, type Choice, type Collaborator } from '../shared';

interface Row extends Collaborator { project: { id: number; title: string }; can_manage: boolean }
interface Resp { collaborators: Row[]; projects: { value: number; label: string }[]; roles: Choice[] }

export default function CollaboratorsListPage() {
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const project = params.get('project') || '';
  const role = params.get('role') || '';
  const [form, setForm] = useState({ search, project, role });
  useEffect(() => setForm({ search, project, role }), [search, project, role]);

  const q = useQuery({
    queryKey: ['projects', 'collaborators-list', search, project, role],
    queryFn: async () => (await api.get<Resp>('/api/projects/collaborators', { params: { search, project, role } })).data,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const p = new URLSearchParams();
    Object.entries(form).forEach(([k, v]) => { if (v) p.set(k, v); });
    setParams(p);
  };

  return (
    <>
      <PageHeader title={<span className="row-tight"><Users size={20} /> Project Collaborators</span>}
        actions={<Link to="/journal-selector/projects/" className="btn btn-secondary"><ArrowLeft size={15} /> Back to Projects</Link>} />

      <section className="panel" style={{ marginBottom: 18 }}>
        <form className="panel-body proj-filters" style={{ gridTemplateColumns: '2fr 1.5fr 1.5fr auto' }} onSubmit={submit}>
          <label className="field"><span className="field-label">Search:</span>
            <input className="input" maxLength={255} placeholder="Search by name, email, or role..." value={form.search}
              onChange={(e) => setForm({ ...form, search: e.target.value })} />
          </label>
          <label className="field"><span className="field-label">Project:</span>
            <select className="input" value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })}>
              <option value="">All Projects</option>
              {q.data?.projects.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </label>
          <label className="field"><span className="field-label">Role:</span>
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="">All Roles</option>
              {q.data?.roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </label>
          <div className="row-tight">
            <button type="submit" className="btn btn-primary"><Search size={14} /> Search</button>
            <button type="button" className="btn btn-secondary" onClick={() => setParams(new URLSearchParams())}><X size={14} /> Clear</button>
          </div>
        </form>
      </section>

      {q.isLoading && <Loading />}
      {q.error && <ErrorNotice error={q.error} />}
      {q.data && (q.data.collaborators.length ? (
        <section className="panel">
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th>Collaborator</th><th>Project</th><th>Role</th><th>Joined</th><th>Actions</th></tr></thead>
              <tbody>
                {q.data.collaborators.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <div className="row-tight">
                        <Avatar text={c.user.initials} />
                        <div><div>{c.user.full_name}</div><div className="small muted">{c.user.email}</div></div>
                      </div>
                    </td>
                    <td><Link to={`/journal-selector/projects/${c.project.id}/`} style={{ color: 'var(--accent)' }}>{c.project.title}</Link></td>
                    <td><StatusBadge value={c.role} label={c.role_display} /></td>
                    <td>{formatDate(c.joined_at)}</td>
                    <td>
                      <div className="actions">
                        <Link to={`/journal-selector/projects/${c.project.id}/collaborators/`} className="btn btn-ghost btn-icon" title="View Project Collaborators"><Eye size={14} /></Link>
                        {c.can_manage && <>
                          <Link to={`/journal-selector/projects/${c.project.id}/collaborators/${c.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit Role"><Edit size={14} /></Link>
                          <Link to={`/journal-selector/projects/${c.project.id}/collaborators/${c.id}/delete/`} className="btn btn-ghost btn-icon" title="Remove Collaborator"><Trash2 size={14} /></Link>
                        </>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <section className="panel">
          <Empty title="No Collaborators Found">No collaborators match your search criteria or you don't have any projects with collaborators yet.</Empty>
        </section>
      ))}
    </>
  );
}
