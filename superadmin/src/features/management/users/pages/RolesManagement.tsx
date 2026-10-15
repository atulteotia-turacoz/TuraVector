import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Pencil, Plus, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import { Badge, ErrorNotice, Loading, PageHeader, Panel, useConfirm } from '@/components/ui';
import { truncate, useErrorToast, useFlash, usePageData, type ActionResult, type PermissionItem, type RoleItem } from '../shared';

type RoleCard = RoleItem & { permission_count: number; permissions: PermissionItem[] };

export default function RolesManagement() {
  const q = usePageData<{ roles: RoleCard[] }>(['legacy-roles'], '/api/rbac/legacy/roles');
  const confirm = useConfirm();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;

  const del = async (role: RoleCard) => {
    if (!(await confirm({ message: 'Are you sure you want to delete this role?', danger: true, confirmLabel: 'Delete' }))) return;
    try {
      const { data } = await api.post<ActionResult>('/api/rbac/legacy/roles', { action: 'delete_role', role_id: String(role.id) });
      flash(data.messages, data.message);
    } catch (e) { showError(e); }
    qc.invalidateQueries({ queryKey: ['users'] });
  };

  return (
    <div className="stack-lg">
      <PageHeader title="Roles & Permissions" eyebrow="Roles & Permissions Management" subtitle="Manage user roles and their associated permissions"
        actions={<>
          <Link className="btn btn-secondary" to="/library/manage-users/"><ArrowLeft size={14} /> Back to All Users</Link>
          <Link className="btn btn-primary" to="/library/role/create/"><Plus size={14} /> Create New Role</Link>
        </>} />
      {q.data.roles.length === 0 ? (
        <div className="notice notice-accent">No roles found. Create your first role to get started.</div>
      ) : (
        <div className="grid-3">
          {q.data.roles.map((role) => (
            <Panel key={role.id} title={<span className="row-tight wrap">{role.name}{role.is_system_role && <Badge tone="warn">System Role</Badge>}</span>}
              footer={<div className="row">
                <Link className="btn btn-secondary btn-sm" to={`/library/role/${role.id}/edit/`}><Pencil size={13} /> Edit</Link>
                {!role.is_system_role && <button className="btn btn-danger btn-sm" onClick={() => del(role)}><Trash2 size={13} /> Delete</button>}
              </div>}>
              <p className="muted small">{role.description || 'No description'}</p>
              <div className="small"><strong>Permissions:</strong></div>
              {role.permission_count > 0 ? (
                <div className="row-tight wrap" style={{ marginTop: 6 }}>
                  {role.permissions.map((p) => <Badge key={p.id}>{p.action_display} - {truncate(p.module_display, 20)}</Badge>)}
                  {role.permission_count > 5 && <Badge tone="accent">+{role.permission_count - 5} more</Badge>}
                </div>
              ) : <p className="muted small">No permissions assigned</p>}
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
