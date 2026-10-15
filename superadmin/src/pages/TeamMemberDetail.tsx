/**
 * One member's review work: where they are assigned (and assigning them elsewhere), numbers per
 * university / organisation and every review assignment.
 */
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Shield, UserPlus, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate, timeAgo } from '@/lib/format';
import { Badge, ErrorNotice, Loading, PageHeader, Pagination, Panel, Stat, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

interface Counts { assigned: number; completed: number; pending: number; in_progress: number; overdue: number }
interface Item {
  id: number; organisation_id: number | null; organisation: string; document_id: number; document_number: string;
  document_name: string; version: string; assigned_at: string | null; review_date: string | null; started_at: string | null;
  completed_at: string | null; status: 'completed' | 'overdue' | 'in_progress' | 'pending'; status_label: string; remarks: string;
}
interface Detail {
  organisation: { id: number; name: string; kind: string };
  member: { user_id: number; username: string; email: string; phone: string | null; name: string; user_type_display: string;
    is_active: boolean; last_login: string | null; date_joined: string | null; role: string };
  assignments: { id: number; organisation_id: number; organisation: string; role: string; role_label: string; designation: string; since: string | null }[];
  totals: Counts;
  by_organisation: (Counts & { organisation_id: number | null; organisation: string })[];
  items: Item[];
}

const STATUS_TONE: Record<Item['status'], 'ok' | 'danger' | 'warn' | undefined> = {
  completed: 'ok', overdue: 'danger', in_progress: 'warn', pending: undefined,
};
const PAGE = 20;

export default function TeamMemberDetail() {
  const { orgId, userId } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const key = ['admin', 'organisations', 'member-reviews', orgId, userId];
  const q = useQuery({
    queryKey: key,
    queryFn: async () => (await api.get<Detail>(`/api/superadmin/organisations/${orgId}/members/${userId}/reviews`)).data,
  });
  const orgs = useQuery({
    queryKey: ['admin', 'organisations', 'clients'],
    queryFn: async () => (await api.get<{ organisations: { id: number; name: string; kind: string }[] }>('/api/superadmin/organisations', { params: { status: 'active' } }))
      .data.organisations.filter((o) => o.kind === 'university' || o.kind === 'organisation'),
  });
  // no default role: choosing PoC or Reviewer is deliberate
  const [assign, setAssign] = useState({ org: '', role: '', designation: '' });
  const [filter, setFilter] = useState({ org: '', status: '' });
  const [page, setPage] = useState(1);

  const items = useMemo(() => (q.data?.items ?? []).filter((i) =>
    (!filter.org || String(i.organisation_id) === filter.org) && (!filter.status || i.status === filter.status)), [q.data, filter]);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { organisation: org, member: m, assignments, totals, by_organisation: byOrg } = q.data;
  const pages = Math.max(1, Math.ceil(items.length / PAGE));
  const current = Math.min(page, pages);
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin', 'organisations'] });

  const addAssignment = async () => {
    if (!assign.org || !assign.role) return;
    try {
      const { data } = await api.post(`/api/superadmin/organisations/${assign.org}/assignments`,
        { user_id: m.user_id, role: assign.role, designation: assign.designation });
      toast.success(data.message);
      setAssign({ org: '', role: '', designation: '' });
      await refresh();
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const removeAssignment = async (a: Detail['assignments'][number]) => {
    if (!(await confirm({ title: 'Remove assignment', danger: true, confirmLabel: 'Remove',
      message: `${m.name} will no longer be ${a.role_label} for ${a.organisation}. Reviews already assigned stay as they are.` }))) return;
    try {
      const { data } = await api.delete(`/api/superadmin/organisations/${a.organisation_id}/assignments/${a.id}`);
      toast.success(data.message);
      await refresh();
    } catch (err) { toast.error(errorMessage(err)); }
  };

  return (
    <>
      <Crumbs items={[{ label: 'Organisations', to: '/organisations/' }, { label: org.name, to: `/organisations/${org.id}/?tab=members` }, { label: m.name }]} />
      <PageHeader eyebrow={org.name} title={m.name}
        subtitle={<span className="row-tight wrap">
          <Badge>{m.user_type_display}</Badge>
          {m.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Inactive</Badge>}
          <span className="small muted">{m.username} · {m.email}{m.phone ? ` · ${m.phone}` : ''} · last sign-in {m.last_login ? timeAgo(m.last_login) : 'never'}</span>
        </span>}
        actions={<div className="row-tight">
          <Link className="btn btn-secondary btn-sm" to={`/library/user/${m.user_id}/edit/`}><Pencil size={13} /> Edit user</Link>
          <Link className="btn btn-secondary btn-sm" to={`/library/user/${m.user_id}/permissions/`}><Shield size={13} /> Permissions</Link>
        </div>} />

      <div className="stat-grid">
        <Stat value={totals.assigned} label="Reviews assigned" />
        <Stat value={totals.completed} label="Completed" note={totals.assigned ? `${Math.round((totals.completed / totals.assigned) * 100)}% done` : undefined} />
        <Stat value={totals.pending} label="Pending" note={`${totals.in_progress} started`} />
        <Stat value={totals.overdue} label="Overdue" note={totals.overdue ? 'Past the review date' : 'None'} />
      </div>

      <div className="grid-2 tm-grid">
        <Panel title="Assigned to" flush>
          <div className="org-add">
            <select className="input grow" value={assign.org} onChange={(e) => setAssign((a) => ({ ...a, org: e.target.value }))} aria-label="University or organisation">
              <option value="">Choose a university / organisation…</option>
              {(orgs.data ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
            <select className="input" style={{ width: 170 }} value={assign.role} onChange={(e) => setAssign((a) => ({ ...a, role: e.target.value }))} aria-label="Role">
              <option value="" disabled>Role…</option><option value="poc">PoC</option><option value="reviewer">Reviewer</option>
              <option value="finance">Financial Manager</option>
            </select>
            <input className="input" style={{ width: 150 }} placeholder="Designation" value={assign.designation}
              onChange={(e) => setAssign((a) => ({ ...a, designation: e.target.value }))} />
            <button className="btn btn-primary" disabled={!assign.org || !assign.role} onClick={addAssignment}><UserPlus size={14} /> Assign</button>
          </div>
          {assignments.length === 0
            ? <div className="panel-body muted small">Not assigned to any university or organisation yet.</div>
            : (
              <table className="tbl">
                <thead><tr><th>Workspace</th><th>Role</th><th>Since</th><th /></tr></thead>
                <tbody>
                  {assignments.map((a) => (
                    <tr key={a.id}>
                      <td><Link className="act" to={`/organisations/${a.organisation_id}/?tab=pocs`}>{a.organisation}</Link>
                        <span className="tiny faint" style={{ display: 'block' }}>{a.designation}</span></td>
                      <td><Badge tone="accent">{a.role_label}</Badge></td>
                      <td className="nowrap small">{a.since ? formatDate(a.since) : ''}</td>
                      <td><button className="btn btn-ghost btn-sm" onClick={() => removeAssignment(a)}><X size={13} /> Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </Panel>

        <Panel title="By university / organisation" flush>
          {byOrg.length === 0
            ? <div className="panel-body muted small">No review assignments yet.</div>
            : (
              <table className="tbl">
                <thead><tr><th>Workspace</th><th className="num">Assigned</th><th className="num">Done</th><th className="num">Pending</th><th className="num">Overdue</th></tr></thead>
                <tbody>
                  {byOrg.map((r) => (
                    <tr key={r.organisation} className="clickable" onClick={() => { setFilter((f) => ({ ...f, org: r.organisation_id ? String(r.organisation_id) : '' })); setPage(1); }}>
                      <td>{r.organisation}</td>
                      <td className="num">{r.assigned}</td>
                      <td className="num">{r.completed}</td>
                      <td className="num">{r.pending}{r.in_progress > 0 && <span className="tiny faint" style={{ display: 'block' }}>{r.in_progress} started</span>}</td>
                      <td className="num">{r.overdue > 0 ? <Badge tone="danger">{r.overdue}</Badge> : <span className="faint">0</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </Panel>
      </div>

      <Panel title={`Review assignments (${items.length}${items.length !== q.data.items.length ? ` of ${q.data.items.length}` : ''})`} flush>
        <div className="org-filters">
          <select className="input" value={filter.org} onChange={(e) => { setFilter((f) => ({ ...f, org: e.target.value })); setPage(1); }} aria-label="Workspace">
            <option value="">All universities / organisations</option>
            {byOrg.map((r) => <option key={r.organisation} value={r.organisation_id ?? ''}>{r.organisation}</option>)}
          </select>
          <select className="input" value={filter.status} onChange={(e) => { setFilter((f) => ({ ...f, status: e.target.value })); setPage(1); }} aria-label="Status">
            <option value="">All statuses</option>
            <option value="pending">Pending</option><option value="in_progress">In progress</option>
            <option value="overdue">Overdue</option><option value="completed">Completed</option>
          </select>
          {(filter.org || filter.status) && <button className="btn btn-ghost btn-sm" onClick={() => { setFilter({ org: '', status: '' }); setPage(1); }}><X size={13} /> Clear</button>}
        </div>
        {items.length === 0
          ? <div className="panel-body muted small">No review assignments match.</div>
          : (
            <div className="table-wrap">
              <table className="tbl">
                <thead><tr><th>Document</th><th>Workspace</th><th>Status</th><th>Review date</th><th>Completed</th></tr></thead>
                <tbody>
                  {items.slice((current - 1) * PAGE, current * PAGE).map((i) => (
                    <tr key={i.id}>
                      <td className="tm-doc"><Link className="act" to={`/documents/document/${i.document_id}/change/`}>{i.document_name}</Link>
                        <span className="tiny faint mono" style={{ display: 'block' }}>{i.version}</span></td>
                      <td className="small">{i.organisation}</td>
                      <td><Badge tone={STATUS_TONE[i.status]}>{i.status_label}</Badge></td>
                      <td className="nowrap small">{i.review_date ? formatDate(i.review_date) : '—'}</td>
                      <td className="nowrap small">{i.completed_at ? formatDate(i.completed_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {pages > 1 && <div className="org-pager"><Pagination page={current} pages={pages} total={items.length} onChange={setPage} /></div>}
      </Panel>
    </>
  );
}
