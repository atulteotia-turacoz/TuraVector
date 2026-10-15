import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Eye, Key, KeyRound, Pencil, Search, Shield, UserCheck, UserPlus, UserX, Upload, X, Users } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '../../auth';
import { Badge, DataTable, Empty, ErrorNotice, Loading, PageHeader, Panel, Stat, useConfirm, type Column } from '@/components/ui';
import { formatDate } from '@/lib/format';
import { ActiveBadge, timeHM, useErrorToast, useFlash, usePageData, type ActionResult, type UserRow } from '../shared';

interface ManageUsersData {
  users: UserRow[];
  total_users: number; active_users: number; inactive_users: number;
  user_type_stats: { code: string; name: string; count: number }[];
  user_types: { value: string; label: string }[];
  /** workspaces to filter by (superadmin only) */
  organisations: { id: number; name: string }[] | null;
  /** workspace shown: an id, "all" or "none" */
  organisation_filter: string;
}

export default function ManageUsers() {
  const { user: me } = useAuth();
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const userType = params.get('user_type') || '';
  const status = params.get('status') || '';
  const organisation = params.get('organisation') || '';
  const [form, setForm] = useState({ search, user_type: userType, status, organisation });
  const q = usePageData<ManageUsersData>(['manage', search, userType, status, organisation], '/api/users/manage', { search, user_type: userType, status, organisation });
  const qc = useQueryClient();
  const confirm = useConfirm();
  const flash = useFlash();
  const showError = useErrorToast();

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;
  const shownOrg = form.organisation || d.organisation_filter;

  const toggle = async (u: UserRow, deactivate: boolean) => {
    const ok = await confirm({
      title: deactivate ? 'Deactivate user' : 'Activate user',
      message: `Are you sure you want to ${deactivate ? 'deactivate' : 'activate'} this user?`,
      danger: deactivate, confirmLabel: deactivate ? 'Deactivate' : 'Activate',
    });
    if (!ok) return;
    try {
      const { data } = await api.post<ActionResult>(`/api/users/${u.id}/toggle-status`);
      flash(data.messages, data.message);
    } catch (e) { showError(e); }
    qc.invalidateQueries({ queryKey: ['users'] });
  };

  const columns: Column<UserRow>[] = [
    // name, username and email in one column so the Actions column stays on screen
    { key: 'name', header: 'User', value: (u) => `${u.first_name} ${u.last_name} ${u.username} ${u.email}`,
      render: (u) => (
        <div className="users-cell">
          <div className="row-tight wrap"><strong>{u.first_name} {u.last_name}</strong>{u.is_manager && <Badge tone="accent">Manager</Badge>}</div>
          <div className="tiny muted"><code className="mono">{u.username}</code> · {u.email}</div>
        </div>
      ) },
    { key: 'user_type_display', header: 'User Type', render: (u) => <Badge>{u.user_type_display}</Badge> },
    { key: 'is_active', header: 'Status', value: (u) => (u.is_active ? 'Active' : 'Inactive'), render: (u) => <ActiveBadge active={u.is_active} /> },
    { key: 'last_login', header: 'Last Login', value: (u) => u.last_login || '',
      render: (u) => u.last_login ? <span className="nowrap">{formatDate(u.last_login)}<br /><span className="tiny muted">{timeHM(u.last_login)}</span></span> : <Badge>Never</Badge> },
    { key: 'date_joined', header: 'Joined', value: (u) => u.date_joined || '',
      render: (u) => <span className="nowrap">{formatDate(u.date_joined)}</span> },
    { key: 'document_count', header: 'Documents', render: (u) => <Badge>{u.document_count ?? 0}</Badge> },
    { key: 'actions', header: 'Actions', sortable: false, render: (u) => {
      const canDeactivate = u.is_active && !u.is_superuser && u.username !== 'admin';
      return (
        <div className="row-tight nowrap">
          <Link className="btn btn-ghost btn-icon" title="View Profile" to={`/library/user/${u.id}/view/`}><Eye size={14} /></Link>
          <Link className="btn btn-ghost btn-icon" title="Edit User" to={`/library/user/${u.id}/edit/`}><Pencil size={14} /></Link>
          <Link className="btn btn-ghost btn-icon" title="Manage Permissions" to={`/library/user/${u.id}/permissions/`}><Shield size={14} /></Link>
          <Link className="btn btn-ghost btn-icon" title="Change Password" to={`/library/user/${u.id}/change-password/`}><Key size={14} /></Link>
          {me?.is_superuser && <Link className="btn btn-ghost btn-icon" title="View Password" to={`/library/user/${u.id}/view-password/`}><KeyRound size={14} /></Link>}
          {canDeactivate
            ? <button className="btn btn-ghost btn-icon" title="Deactivate" onClick={() => toggle(u, true)}><UserX size={14} /></button>
            : <button className="btn btn-ghost btn-icon" title="Activate" onClick={() => toggle(u, false)}><UserCheck size={14} /></button>}
        </div>
      );
    } },
  ];
  // with one workspace chosen every row is in it, so the column only shows for "all" / "none"
  if (d.organisations && !/^\d+$/.test(shownOrg)) {
    columns.splice(1, 0, { key: 'organisation', header: 'Workspace', value: (u) => u.organisation || '',
      render: (u) => u.organisation ?? <span className="faint">{u.is_superuser ? 'Platform' : 'None'}</span> });
  }

  const apply = (next: typeof form) => {
    const p = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => v && p.set(k, v));
    setParams(p);
  };
  const filtered = !!(search || userType || status || organisation);

  return (
    <div className="stack-lg">
      <PageHeader title="All Users"
        actions={<Link className="btn btn-secondary" to="/"><ArrowLeft size={14} /> Back to Dashboard</Link>} />

      <div className="stat-grid">
        <Stat value={d.total_users} label="Total Users" />
        <Stat value={d.active_users} label="Active Users" />
        <Stat value={d.inactive_users} label="Inactive Users" />
        {d.user_type_stats.map((s) => <Stat key={s.code} value={s.count} label={s.name} />)}
      </div>


      <Panel title="Search & Filter Users">
        <form className="users-filter" onSubmit={(e) => { e.preventDefault(); apply(form); }}>
          <label className="field">
            <span className="field-label">Search</span>
            <input className="input" value={form.search} placeholder="Name, email, or username"
              onChange={(e) => setForm({ ...form, search: e.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">User Type</span>
            <select className="input" value={form.user_type} onChange={(e) => setForm({ ...form, user_type: e.target.value })}>
              <option value="">All Types</option>
              {d.user_types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </label>
          {d.organisations && (
            <label className="field">
              <span className="field-label">Workspace</span>
              <select className="input" value={form.organisation} onChange={(e) => setForm({ ...form, organisation: e.target.value })}>
                <option value="">All workspaces</option>
                {d.organisations.map((o) => <option key={o.id} value={String(o.id)}>{o.name}</option>)}
                <option value="none">No workspace</option>
              </select>
            </label>
          )}
          <label className="field">
            <span className="field-label">Status</span>
            <select className="input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
              <option value="">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
          <div className="row users-filter-actions">
            <button className="btn btn-primary" type="submit"><Search size={14} /> Search</button>
            <button className="btn btn-secondary" type="button" onClick={() => { const c = { search: '', user_type: '', status: '', organisation: '' }; setForm(c); apply(c); }}><X size={14} /> Clear</button>
          </div>
        </form>
      </Panel>

      <Panel flush title={<span className="row-tight"><Users size={15} /> Users <Badge>{d.users.length} found</Badge></span>}
        actions={<>
          <Link className="btn btn-secondary btn-sm" to="/library/roles/"><Shield size={14} /> Manage Roles</Link>
          <Link className="btn btn-secondary btn-sm" to="/library/bulk-import-users/"><Upload size={14} /> Bulk Import</Link>
          <Link className="btn btn-primary btn-sm" to="/library/create-user/"><UserPlus size={14} /> Create New User</Link>
        </>}>
        {d.users.length ? (
          <div className="panel-body"><DataTable rows={d.users} columns={columns} rowKey={(u) => u.id} pageSize={25} /></div>
        ) : (
          <Empty title="No users found">
            {filtered
              ? <>Try adjusting your search criteria or <a className="act" href="/library/manage-users/" onClick={(e) => { e.preventDefault(); apply({ search: '', user_type: '', status: '', organisation: '' }); }}>clear all filters</a>.</>
              : 'No users are available in the system.'}
          </Empty>
        )}
      </Panel>
    </div>
  );
}
