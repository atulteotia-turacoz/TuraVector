/** Pages for library/permission_views.py (the "comprehensive" permission management screens). */
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Eye, KeyRound, LayoutDashboard, Pencil, Plus, Shield, Trash2, UserPlus, Users, X } from 'lucide-react';
import { api } from '@/lib/api';
import { Badge, DataTable, Empty, ErrorNotice, Field, Loading, PageHeader, Pagination, Panel, Stat, useConfirm, type Column } from '@/components/ui';
import { formatDateTime } from '@/lib/format';
import { useErrorToast, useFlash, usePageData, type ActionResult, type PermissionGroup, type PermissionItem, type RoleItem, type UserRow } from '../shared';

/* ------------------------------------------------------------------ dashboard */
interface DashData {
  stats: Record<'total_permissions' | 'total_roles' | 'total_users' | 'total_role_assignments' | 'content_lab_permissions' | 'other_documents_permissions', number>;
  recent_role_assignments: { id: number; role_name: string; user_name: string; assigned_by: string | null; assigned_at: string }[];
}

export function PermissionDashboard() {
  const q = usePageData<DashData>(['perm-dashboard'], '/api/rbac/dashboard');
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { stats, recent_role_assignments } = q.data;
  return (
    <div className="stack-lg">
      <PageHeader title="Permission Management Dashboard" subtitle="Comprehensive role and permission management system"
        actions={<Link className="btn btn-secondary" to="/"><ArrowLeft size={14} /> Back to Dashboard</Link>} />
      <Panel title="System Overview">
        <div className="stat-grid">
          <Stat value={stats.total_permissions} label="Total Permissions" />
          <Stat value={stats.total_roles} label="Active Roles" />
          <Stat value={stats.total_users} label="System Users" />
          <Stat value={stats.total_role_assignments} label="Role Assignments" />
          <Stat value={stats.content_lab_permissions} label="Content Lab Permissions" />
          <Stat value={stats.other_documents_permissions} label="Other Documents Permissions" />
        </div>
      </Panel>
      <Panel title="Quick Actions">
        <div className="grid-3">
          <div className="stack">
            <div className="section-title">Role Management</div>
            <Link className="btn btn-primary" to="/library/permissions/roles/"><Shield size={14} /> Manage Roles</Link>
            <Link className="btn btn-secondary" to="/library/permissions/roles/create/"><Plus size={14} /> Create New Role</Link>
          </div>
          <div className="stack">
            <div className="section-title">Dashboard Permissions</div>
            <Link className="btn btn-primary" to="/library/permissions/dashboard-access/"><LayoutDashboard size={14} /> Dashboard Access Control</Link>
          </div>
          <div className="stack">
            <div className="section-title">User Management</div>
            <Link className="btn btn-primary" to="/library/manage-users/"><Users size={14} /> Manage Users</Link>
            <Link className="btn btn-secondary" to="/library/create-user/"><UserPlus size={14} /> Create New User</Link>
          </div>
        </div>
      </Panel>
      <Panel title="Recent Role Assignments">
        {recent_role_assignments.length ? (
          <div className="stack">
            {recent_role_assignments.map((a) => (
              <div key={a.id} className="row between wrap">
                <div>
                  <div>Role "{a.role_name}" assigned to {a.user_name}</div>
                  <div className="tiny muted">{a.assigned_by ? `Assigned by ${a.assigned_by}` : 'System assignment'}</div>
                </div>
                <span className="tiny muted">{formatDateTime(a.assigned_at)}</span>
              </div>
            ))}
          </div>
        ) : <div className="muted">No recent role assignments</div>}
      </Panel>
    </div>
  );
}

/* ------------------------------------------------------------------ roles list */
type RoleRow = RoleItem & { permission_count: number; user_count: number };

export function CompRoles() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get('page') || '1') || 1;
  const q = usePageData<{ roles: RoleRow[]; page: number; pages: number; total: number; can_create: boolean; can_edit: boolean; can_delete: boolean }>(
    ['comp-roles', page], '/api/rbac/roles', { page });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;
  return (
    <div className="stack-lg">
      <PageHeader title="Role Management" subtitle="Manage user roles and their associated permissions"
        actions={<>
          <Link className="btn btn-secondary" to="/library/permissions/dashboard/"><ArrowLeft size={14} /> Back to Permissions</Link>
          {d.can_create && <Link className="btn btn-primary" to="/library/permissions/roles/create/"><Plus size={14} /> Create New Role</Link>}
        </>} />
      {d.roles.length === 0 ? (
        <div className="notice notice-accent">No roles found. Create your first role to get started.</div>
      ) : (
        <div className="grid-3">
          {d.roles.map((r) => (
            <Panel key={r.id} title={<span className="row-tight wrap">{r.name}{r.is_system_role && <Badge tone="warn">System Role</Badge>}</span>}
              footer={<div className="row">
                <Link className="btn btn-secondary btn-sm" to={`/library/permissions/roles/${r.id}/`}><Eye size={13} /> View</Link>
                {d.can_edit && <Link className="btn btn-secondary btn-sm" to={`/library/permissions/roles/${r.id}/edit/`}><Pencil size={13} /> Edit</Link>}
              </div>}>
              <p className="muted small">{r.description || 'No description'}</p>
              <div className="row-tight wrap"><Badge>{r.permission_count} permissions</Badge><Badge>{r.user_count} users</Badge></div>
            </Panel>
          ))}
        </div>
      )}
      <Pagination page={d.page} pages={d.pages} total={d.total} onChange={(p) => setParams({ page: String(p) })} />
    </div>
  );
}

/* ------------------------------------------------------------------ create role (name + description) */
export function CompRoleCreate() {
  const navigate = useNavigate();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post<ActionResult & { id: number }>('/api/rbac/roles', { name, description });
      flash(data.messages, data.message);
      qc.invalidateQueries({ queryKey: ['users'] });
      navigate(`/library/permissions/roles/${data.id}/`);
    } catch (err) { showError(err); setBusy(false); }
  };
  return (
    <form className="stack-lg" onSubmit={submit}>
      <PageHeader title="Create New Role" subtitle="Define permissions and access levels for your organization"
        actions={<Link className="btn btn-secondary" to="/library/roles/"><ArrowLeft size={14} /> Back to Roles Management</Link>} />
      <Panel>
        <div className="form-grid">
          <Field label="Role Name *" help="Choose a descriptive name for this role">
            <input className="input" required value={name} placeholder="e.g., Content Editor, Research Analyst" onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Description" help="Optional: Describe the role's purpose">
            <input className="input" value={description} placeholder="Brief description of role responsibilities" onChange={(e) => setDescription(e.target.value)} />
          </Field>
        </div>
      </Panel>
      <div className="row">
        <button className="btn btn-primary" type="submit" disabled={busy}><Plus size={14} /> Create Role</button>
        <Link className="btn btn-secondary" to="/library/roles/"><X size={14} /> Cancel</Link>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ role detail */
interface RoleDetailData {
  role: RoleItem;
  permissions_by_dashboard: PermissionGroup[];
  users_with_role: { id: number; user: UserRow; assigned_at: string; expires_at: string | null }[];
  available_permissions: PermissionItem[] | null;
  can_edit: boolean; can_assign_permissions: boolean;
}

export function CompRoleDetail() {
  const { roleId } = useParams();
  const q = usePageData<RoleDetailData>(['comp-role', roleId], `/api/rbac/roles/${roleId}`);
  const qc = useQueryClient();
  const flash = useFlash();
  const showError = useErrorToast();
  const confirm = useConfirm();
  const [permId, setPermId] = useState('');
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;

  const assign = async (e: FormEvent) => {
    e.preventDefault();
    if (!permId) return;
    try {
      const { data } = await api.post<ActionResult>(`/api/rbac/roles/${d.role.id}/assign-permission`, { permission_id: Number(permId) });
      flash(null, data.message);
      setPermId('');
    } catch (err) { showError(err); }
    qc.invalidateQueries({ queryKey: ['users'] });
  };
  const remove = async (p: PermissionItem) => {
    if (!(await confirm({ message: `Remove permission "${p.name}" from role "${d.role.name}"?`, danger: true }))) return;
    try {
      const { data } = await api.delete<ActionResult>(`/api/rbac/roles/${d.role.id}/permissions/${p.id}`);
      flash(null, data.message);
    } catch (err) { showError(err); }
    qc.invalidateQueries({ queryKey: ['users'] });
  };

  return (
    <div className="stack-lg">
      <PageHeader title={`Role: ${d.role.name}`} subtitle={d.role.description || 'No description provided'}
        actions={<>
          <Link className="btn btn-secondary" to="/library/permissions/roles/"><ArrowLeft size={14} /> Back to Roles</Link>
          {d.can_edit && <Link className="btn btn-primary" to={`/library/permissions/roles/${d.role.id}/edit/`}><Pencil size={14} /> Edit Role</Link>}
        </>} />
      <div className="detail-grid">
        <Panel title="Permissions">
          {d.permissions_by_dashboard.length ? (
            <div className="stack-lg">
              {d.permissions_by_dashboard.map((g) => (
                <div key={g.dashboard} className="stack">
                  <div className="section-title">{g.dashboard}</div>
                  {g.modules.map((m) => (
                    <div key={m.module} className="well">
                      <div className="small"><strong>{m.module}</strong></div>
                      <div className="row-tight wrap" style={{ marginTop: 6 }}>
                        {m.permissions.map((p) => (
                          <span key={p.id} className="badge row-tight">{p.action}
                            {d.can_assign_permissions && <button className="btn-ghost" title="Remove" onClick={() => remove(p)}><X size={11} /></button>}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : <div className="muted">No permissions assigned</div>}
          {d.can_assign_permissions && d.available_permissions && (
            <form className="row" style={{ marginTop: 16 }} onSubmit={assign}>
              <select className="input grow" value={permId} onChange={(e) => setPermId(e.target.value)}>
                <option value="">Select a permission...</option>
                {d.available_permissions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <button className="btn btn-primary" type="submit"><Plus size={14} /> Assign Permission</button>
            </form>
          )}
        </Panel>
        <Panel title={`Users with this Role (${d.users_with_role.length})`}>
          {d.users_with_role.length ? (
            <div className="stack">
              {d.users_with_role.map((ur) => (
                <div key={ur.id}>
                  <div><strong>{`${ur.user.first_name} ${ur.user.last_name}`.trim()}</strong></div>
                  <div className="tiny muted">{ur.user.email}</div>
                </div>
              ))}
            </div>
          ) : <div className="muted">No users have this role</div>}
        </Panel>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ user roles */
interface UserRolesData {
  target_user: UserRow;
  user_roles: { id: number; role: RoleItem; assigned_at: string; expires_at: string | null }[];
  available_roles: RoleItem[];
}

export function CompUserRoles() {
  const { userId } = useParams();
  const q = usePageData<UserRolesData>(['comp-user-roles', userId], `/api/rbac/users/${userId}/roles`);
  const qc = useQueryClient();
  const flash = useFlash();
  const showError = useErrorToast();
  const [roleId, setRoleId] = useState('');
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;
  const name = `${d.target_user.first_name} ${d.target_user.last_name}`.trim();
  const post = async (action: string, role_id: string) => {
    try {
      const { data } = await api.post<ActionResult>(`/api/rbac/users/${d.target_user.id}/roles`, { action, role_id });
      flash(data.messages, data.message);
    } catch (err) { showError(err); }
    qc.invalidateQueries({ queryKey: ['users'] });
  };
  return (
    <div className="stack-lg">
      <PageHeader title={`Manage Roles: ${name}`} subtitle={`${d.target_user.email} · ${d.target_user.user_type_display}`}
        actions={<Link className="btn btn-secondary" to="/library/permissions/dashboard-access/"><ArrowLeft size={14} /> Back</Link>} />
      <div className="grid-2">
        <Panel title="Current Roles">
          {d.user_roles.length ? (
            <div className="stack">
              {d.user_roles.map((ur) => (
                <div key={ur.id} className="row between">
                  <div><strong>{ur.role.name}</strong><div className="tiny muted">Assigned {formatDateTime(ur.assigned_at)}{ur.expires_at && ` · Expires ${formatDateTime(ur.expires_at)}`}</div></div>
                  <button className="btn btn-ghost btn-icon" title="Remove role" onClick={() => post('remove', String(ur.role.id))}><Trash2 size={14} /></button>
                </div>
              ))}
            </div>
          ) : <div className="muted">No roles assigned</div>}
        </Panel>
        <Panel title="Assign Role">
          {d.available_roles.length ? (
            <form className="stack" onSubmit={(e) => { e.preventDefault(); if (roleId) { void post('assign', roleId); setRoleId(''); } }}>
              <select className="input" value={roleId} onChange={(e) => setRoleId(e.target.value)}>
                <option value="">Select a role...</option>
                {d.available_roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <div><button className="btn btn-primary btn-sm" type="submit"><Plus size={13} /> Assign Role</button></div>
            </form>
          ) : <div className="muted">No more roles available</div>}
        </Panel>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ user effective permissions */
interface EffectiveData {
  target_user: UserRow;
  user_roles: { id: number; role: RoleItem }[];
  role_permissions: { role: string; permissions: PermissionItem[] }[];
  permissions_by_dashboard: PermissionGroup[];
  total_permissions: number;
}

export function CompUserPermissions() {
  const { userId } = useParams();
  const q = usePageData<EffectiveData>(['comp-user-perms', userId], `/api/rbac/users/${userId}/permissions`);
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;
  const name = `${d.target_user.first_name} ${d.target_user.last_name}`.trim();
  return (
    <div className="stack-lg">
      <PageHeader title={`User Permissions: ${name}`} subtitle={`${d.target_user.email} · ${d.target_user.username} · ${d.target_user.user_type_display}`}
        actions={<Link className="btn btn-secondary" to="/library/permissions/dashboard-access/"><ArrowLeft size={14} /> Back</Link>} />
      <div className="stat-grid">
        <Stat value={d.user_roles.length} label="Roles" />
        <Stat value={d.total_permissions} label="Effective Permissions" />
      </div>
      <Panel title="Assigned Roles">
        {d.role_permissions.length ? (
          <div className="stack">
            {d.role_permissions.map((rp) => (
              <div key={rp.role}><strong>{rp.role}</strong> <span className="muted small">({rp.permissions.length} permissions)</span></div>
            ))}
          </div>
        ) : <div className="muted">No roles assigned</div>}
      </Panel>
      <Panel title="Permissions by Dashboard">
        {d.permissions_by_dashboard.length ? (
          <div className="stack-lg">
            {d.permissions_by_dashboard.map((g) => (
              <div key={g.dashboard} className="stack">
                <div className="section-title">{g.dashboard}</div>
                {g.modules.map((m) => (
                  <div key={m.module} className="row-tight wrap"><span className="small"><strong>{m.module}:</strong></span>
                    {m.permissions.map((p) => <Badge key={p.id}>{p.action}</Badge>)}</div>
                ))}
              </div>
            ))}
          </div>
        ) : <div className="muted">No permissions</div>}
      </Panel>
    </div>
  );
}

/* ------------------------------------------------------------------ dashboard access */
interface AccessData {
  user_dashboard_access: { user: UserRow; can_access_content_lab: boolean; can_access_other_docs: boolean; roles: { id: number; name: string }[] }[];
  role_dashboard_access: { role: RoleItem; has_content_lab: boolean; has_other_docs: boolean; user_count: number }[];
  content_lab_permission: PermissionItem | null;
  other_documents_permission: PermissionItem | null;
  can_edit: boolean;
}

export function DashboardAccess() {
  const q = usePageData<AccessData>(['dashboard-access'], '/api/rbac/dashboard-access');
  const qc = useQueryClient();
  const showError = useErrorToast();
  const [alert, setAlert] = useState<{ tone: 'ok' | 'danger'; text: string } | null>(null);
  const [busyRow, setBusyRow] = useState<number | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;

  const toggle = async (roleId: number, permission: PermissionItem | null, action: 'grant' | 'revoke') => {
    setBusyRow(roleId);
    try {
      const { data } = await api.post<ActionResult>('/api/rbac/toggle-role-dashboard-permission',
        { role_id: roleId, permission_id: permission?.id ?? null, action });
      setAlert({ tone: 'ok', text: data.message || '' });
      await qc.invalidateQueries({ queryKey: ['users', 'dashboard-access'] });
    } catch (err) {
      const m = (err as any)?.response?.data?.detail;
      setAlert({ tone: 'danger', text: typeof m === 'string' ? m : 'An error occurred while updating permissions' });
      if (!m) showError(err);
    } finally {
      setBusyRow(null);
      setTimeout(() => setAlert(null), 5000);
    }
  };

  const cell = (roleId: number, has: boolean, permission: PermissionItem | null) => (
    <span className="row-tight">
      {has ? <Badge tone="ok">Granted</Badge> : <Badge tone="danger">Denied</Badge>}
      {d.can_edit && (
        <button className="btn btn-secondary btn-sm" disabled={busyRow === roleId}
          onClick={() => toggle(roleId, permission, has ? 'revoke' : 'grant')}>{has ? 'Revoke' : 'Grant'}</button>
      )}
    </span>
  );

  type URow = AccessData['user_dashboard_access'][number];
  const userCols: Column<URow>[] = [
    { key: 'user', header: 'User', value: (r) => `${r.user.first_name} ${r.user.last_name} ${r.user.email}`,
      render: (r) => <div><strong>{`${r.user.first_name} ${r.user.last_name}`.trim()}</strong><div className="tiny muted">{r.user.email}</div><div className="tiny muted">{r.user.user_type_display}</div></div> },
    { key: 'roles', header: 'Assigned Roles', value: (r) => r.roles.map((x) => x.name).join(' '),
      render: (r) => <div className="row-tight wrap">{r.roles.length ? r.roles.map((x) => <Badge key={x.id} tone="accent">{x.name}</Badge>) : <span className="muted small">No roles assigned</span>}</div> },
    { key: 'cl', header: 'Content Lab Access', value: (r) => (r.can_access_content_lab ? 1 : 0),
      render: (r) => (r.can_access_content_lab ? <Badge tone="ok">Has Access</Badge> : <Badge tone="danger">No Access</Badge>) },
    { key: 'od', header: 'Other Documents Access', value: (r) => (r.can_access_other_docs ? 1 : 0),
      render: (r) => (r.can_access_other_docs ? <Badge tone="ok">Has Access</Badge> : <Badge tone="danger">No Access</Badge>) },
    { key: 'actions', header: '', sortable: false, render: (r) => (
      <div className="row-tight nowrap">
        <Link className="btn btn-ghost btn-icon" title="Manage User Roles" to={`/library/permissions/users/${r.user.id}/roles/`}><Users size={14} /></Link>
        <Link className="btn btn-ghost btn-icon" title="View User Permissions" to={`/library/permissions/users/${r.user.id}/permissions/`}><KeyRound size={14} /></Link>
      </div>
    ) },
  ];

  return (
    <div className="stack-lg">
      <PageHeader title="Dashboard Permissions Management" subtitle="Control which users and roles can access different dashboards"
        actions={<Link className="btn btn-secondary" to="/library/permissions/dashboard/"><ArrowLeft size={14} /> Back to Permissions</Link>} />
      {alert && <div className={`notice notice-${alert.tone}`}>{alert.text}</div>}

      <Panel title="Role Dashboard Permissions" flush>
        <p className="muted small panel-body" style={{ paddingBottom: 0 }}>Manage which roles have access to each dashboard. Users will inherit permissions from their assigned roles.</p>
        <div className="table-scroll">
          <table className="tbl">
            <thead><tr><th>Role Name</th><th>Users Count</th><th>Content Lab Access</th><th>Other Documents Access</th><th>Actions</th></tr></thead>
            <tbody>
              {d.role_dashboard_access.length === 0 && <tr><td colSpan={5}><Empty title="No roles found" /></td></tr>}
              {d.role_dashboard_access.map((r) => (
                <tr key={r.role.id}>
                  <td><strong>{r.role.name}</strong>{r.role.description && <div className="tiny muted">{r.role.description}</div>}</td>
                  <td><Badge>{r.user_count} user{r.user_count === 1 ? '' : 's'}</Badge></td>
                  <td>{cell(r.role.id, r.has_content_lab, d.content_lab_permission)}</td>
                  <td>{cell(r.role.id, r.has_other_docs, d.other_documents_permission)}</td>
                  <td className="nowrap">
                    <Link className="btn btn-ghost btn-icon" title="View Role Details" to={`/library/permissions/roles/${r.role.id}/`}><Eye size={14} /></Link>
                    {d.can_edit && <Link className="btn btn-ghost btn-icon" title="Edit Role" to={`/library/permissions/roles/${r.role.id}/edit/`}><Pencil size={14} /></Link>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="User Dashboard Access Status">
        <div className="stack">
          <p className="muted small">Overview of which users have access to each dashboard. Access is determined by the roles assigned to each user.</p>
          <div className="notice notice-accent"><strong>Note:</strong> User dashboard access is determined by their assigned roles.
            To change a user's access, assign or remove roles, or modify role permissions above.</div>
          <DataTable rows={d.user_dashboard_access} columns={userCols} rowKey={(r) => r.user.id} empty="No users found" />
        </div>
      </Panel>
    </div>
  );
}
