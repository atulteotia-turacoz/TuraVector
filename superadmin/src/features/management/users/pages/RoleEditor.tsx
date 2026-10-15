/**
 * create_role.html / edit_role.html. Used by both the legacy views (/library/role/...) and the
 * comprehensive permission views (/library/permissions/roles/...), exactly as Django shared the templates.
 */
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Save, Trash2, X } from 'lucide-react';
import { api } from '@/lib/api';
import { ErrorNotice, Field, Loading, PageHeader, Panel, Stat, useConfirm } from '@/components/ui';
import { formatDate } from '@/lib/format';
import { PermissionMatrix } from '../components/PermissionMatrix';
import { apiError, useErrorToast, useFlash, usePageData, type ActionResult, type PermissionGroup, type RoleItem, type UserRow } from '../shared';

interface FormCtx { permissions_by_dashboard: PermissionGroup[]; total_permissions: number }
interface EditCtx extends FormCtx {
  role: RoleItem; current_permission_ids: number[];
  users_with_role: { id: number; user: UserRow; assigned_at: string; expires_at: string | null }[];
}

function useUnsavedWarning(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [active]);
}

export function RoleCreate() {
  const q = usePageData<FormCtx>(['role-create-form'], '/api/rbac/legacy/roles/create');
  const navigate = useNavigate();
  const confirm = useConfirm();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  useUnsavedWarning(!busy && (selected.size > 0 || !!name.trim()));

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { window.alert('Please enter a role name.'); return; }
    if (selected.size === 0 && !(await confirm({ message: 'No permissions selected. Create role without any permissions?' }))) return;
    setBusy(true);
    try {
      const { data } = await api.post<ActionResult>('/api/rbac/legacy/roles/create', { name, description, permissions: [...selected].map(String) });
      flash(data.messages, data.message);
      qc.invalidateQueries({ queryKey: ['users'] });
      navigate('/library/roles/');
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
      <PermissionMatrix groups={q.data.permissions_by_dashboard} selected={selected} onChange={setSelected}
        totalPermissions={q.data.total_permissions} mode="create" />
      <div className="row">
        <button className="btn btn-primary" type="submit" disabled={busy}><Plus size={14} /> {busy ? 'Creating Role...' : 'Create Role'}</button>
        <Link className="btn btn-secondary" to="/library/roles/"><X size={14} /> Cancel</Link>
      </div>
    </form>
  );
}

export function RoleEdit({ variant }: { variant: 'legacy' | 'comprehensive' }) {
  const { roleId } = useParams();
  const base = variant === 'legacy' ? `/api/rbac/legacy/roles/${roleId}` : `/api/rbac/roles/${roleId}/edit`;
  const q = usePageData<EditCtx>(['role-edit', variant, roleId], base);
  const navigate = useNavigate();
  const confirm = useConfirm();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selected, setSelected] = useState<Set<number> | null>(null);
  const [busy, setBusy] = useState(false);

  const original = useMemo(() => {
    if (!q.data) return new Set<number>();
    const visible = new Set(q.data.permissions_by_dashboard.flatMap((g) => g.modules.flatMap((m) => m.permissions.map((p) => p.id))));
    return new Set(q.data.current_permission_ids.filter((id) => visible.has(id)));
  }, [q.data]);

  useEffect(() => {
    if (!q.data) return;
    setName(q.data.role.name);
    setDescription(q.data.role.description || '');
    setSelected(new Set(original));
  }, [q.data, original]);

  const changed = !!selected && (selected.size !== original.size || [...selected].some((id) => !original.has(id)));
  useUnsavedWarning(changed && !busy);

  if (q.isLoading || (q.data && !selected)) return <Loading />;
  if (q.error || !q.data || !selected) return <ErrorNotice error={q.error} />;
  const { role, users_with_role } = q.data;
  const backTo = '/library/roles/';
  const afterSave = variant === 'legacy' ? '/library/roles/' : '/library/permissions/roles/';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { window.alert('Role name is required.'); return; }
    if (selected.size === 0 && !(await confirm({ message: 'No permissions selected. Update role without any permissions?' }))) return;
    setBusy(true);
    try {
      const { data } = await api.post<ActionResult>(base, { action: 'update', name, description, permissions: [...selected].map(String) });
      flash(data.messages, data.message);
      qc.invalidateQueries({ queryKey: ['users'] });
      navigate(afterSave);
    } catch (err) { showError(err); setBusy(false); }
  };

  const remove = async () => {
    if (!(await confirm({ message: `Are you sure you want to delete the role "${role.name}"? This action cannot be undone.`, danger: true, confirmLabel: 'Delete Role' }))) return;
    setBusy(true);
    try {
      const { data } = await api.post<ActionResult>('/api/rbac/legacy/roles', { action: 'delete_role', role_id: String(role.id) });
      flash(data.messages, data.message);
      qc.invalidateQueries({ queryKey: ['users'] });
      navigate(backTo);
    } catch (err) {
      const info = apiError(err);
      showError(err);
      if (info.redirect) navigate(info.redirect);
      setBusy(false);
    }
  };

  return (
    <form className="stack-lg" onSubmit={submit}>
      <PageHeader title={role.name} eyebrow="Edit Role" subtitle={role.description || 'No description provided'}
        actions={<Link className="btn btn-secondary" to={backTo}><ArrowLeft size={14} /> Back to Roles Management</Link>} />
      <Panel>
        <div className="form-grid">
          <Field label="Role Name *" help={role.is_system_role ? 'System roles cannot be renamed' : undefined}>
            <input className="input" required value={name} readOnly={role.is_system_role} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Description">
            <input className="input" value={description} placeholder="Brief description of role responsibilities" onChange={(e) => setDescription(e.target.value)} />
          </Field>
        </div>
      </Panel>
      <div className="stat-grid">
        <Stat value={q.data.current_permission_ids.length} label="Current Permissions" />
        <Stat value={users_with_role.length} label="Assigned Users" />
        <Stat value={formatDate(role.created_at)} label="Created" />
        <Stat value={formatDate(role.updated_at)} label="Last Updated" />
      </div>
      <PermissionMatrix groups={q.data.permissions_by_dashboard} selected={selected} onChange={setSelected} original={original}
        totalPermissions={q.data.total_permissions} mode="edit" />
      {users_with_role.length > 0 && (
        <Panel title={`Users with this Role (${users_with_role.length})`}>
          <div className="grid-3">
            {users_with_role.map((ur) => (
              <div key={ur.id} className="well">
                <div><strong>{`${ur.user.first_name} ${ur.user.last_name}`.trim()}</strong></div>
                <div className="tiny muted">{ur.user.email}</div>
                <div className="tiny muted">Assigned {formatDate(ur.assigned_at)}</div>
                {ur.expires_at && <div className="tiny muted">Expires {formatDate(ur.expires_at)}</div>}
              </div>
            ))}
          </div>
        </Panel>
      )}
      <div className="row">
        <button className="btn btn-primary" type="submit" disabled={busy}><Save size={14} /> {busy ? 'Updating Role...' : 'Update Role'}</button>
        {!role.is_system_role && <button className="btn btn-danger" type="button" disabled={busy} onClick={remove}><Trash2 size={14} /> Delete Role</button>}
        <Link className="btn btn-secondary" to={backTo}><X size={14} /> Cancel</Link>
      </div>
      {changed && <div className="notice notice-warn users-unsaved">You have unsaved changes</div>}
    </form>
  );
}
