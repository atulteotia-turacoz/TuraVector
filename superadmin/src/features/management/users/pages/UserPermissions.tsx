/** library/user_permissions.html — roles and direct permission overrides for one user. */
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check, Plus, Trash2, X } from 'lucide-react';
import { api } from '@/lib/api';
import { Badge, ErrorNotice, Loading, PageHeader, Panel, useConfirm } from '@/components/ui';
import { ActiveBadge, useErrorToast, useFlash, usePageData, type ActionResult, type PermissionGroup, type PermissionItem, type RoleItem, type UserRow } from '../shared';

interface Data {
  managed_user: UserRow;
  user_roles: { id: number; role: RoleItem }[];
  user_permissions: { id: number; is_granted: boolean; reason: string; permission: PermissionItem }[];
  available_roles: RoleItem[];
  permissions_by_dashboard: PermissionGroup[];
}

export default function UserPermissions() {
  const { userId } = useParams();
  const q = usePageData<Data>(['user-permissions', userId], `/api/users/${userId}/permissions`);
  const qc = useQueryClient();
  const flash = useFlash();
  const showError = useErrorToast();
  const confirm = useConfirm();
  const [roleId, setRoleId] = useState('');

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { managed_user: u, user_roles, user_permissions, available_roles, permissions_by_dashboard } = q.data;
  const fullName = `${u.first_name} ${u.last_name}`.trim();

  const post = async (body: Record<string, string>) => {
    try {
      const { data } = await api.post<ActionResult>(`/api/users/${u.id}/permissions`, body);
      flash(data.messages, data.message);
    } catch (e) { showError(e); }
    qc.invalidateQueries({ queryKey: ['users'] });
  };

  return (
    <div className="stack-lg">
      <PageHeader title={`Permissions for ${fullName}`}
        actions={<Link className="btn btn-secondary" to="/library/manage-users/"><ArrowLeft size={14} /> Back to Users</Link>} />
      <Panel>
        <div className="between wrap row">
          <div>
            <h3 style={{ margin: 0 }}>{fullName}</h3>
            <div className="small muted">{u.email} | {u.username} | {u.user_type_display}</div>
          </div>
          <div className="row-tight">
            <ActiveBadge active={u.is_active} />
            {u.is_superuser && <Badge tone="danger">Superuser</Badge>}
          </div>
        </div>
      </Panel>

      <div className="grid-2">
        <Panel title="Assigned Roles">
          {user_roles.length ? (
            <div className="row-tight wrap">
              {user_roles.map((ur) => (
                <span key={ur.id} className="badge badge-accent row-tight">
                  {ur.role.name}
                  <button className="btn-ghost" title="Remove role" onClick={async () => {
                    if (await confirm({ message: 'Are you sure you want to remove this role?', danger: true })) {
                      await post({ action: 'remove_role', role_id: String(ur.role.id) });
                    }
                  }}><X size={11} /></button>
                </span>
              ))}
            </div>
          ) : <p className="muted">No roles assigned</p>}
          {available_roles.length > 0 && (
            <>
              <hr className="hairline" style={{ margin: '16px 0' }} />
              <form className="stack" onSubmit={async (e) => { e.preventDefault(); await post({ action: 'assign_role', role_id: roleId }); setRoleId(''); }}>
                <label className="field">
                  <span className="field-label">Assign New Role</span>
                  <select className="input" value={roleId} onChange={(e) => setRoleId(e.target.value)}>
                    <option value="">Select a role...</option>
                    {available_roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </select>
                </label>
                <div><button className="btn btn-primary btn-sm" type="submit"><Plus size={13} /> Assign Role</button></div>
              </form>
            </>
          )}
        </Panel>

        <Panel title="Direct Permission Overrides">
          {user_permissions.length ? (
            <div className="stack">
              {user_permissions.map((p) => (
                <div key={p.id} className="row between">
                  <div>
                    <div className="tiny muted">{p.permission.module_display}</div>
                    <strong>{p.permission.action_display}</strong> <Badge tone={p.is_granted ? 'ok' : 'danger'}>{p.is_granted ? 'Granted' : 'Denied'}</Badge>
                    {p.reason && <div className="tiny muted">{p.reason}</div>}
                  </div>
                  <button className="btn btn-ghost btn-icon" title="Remove override"
                    onClick={() => post({ action: 'remove_permission', permission_id: String(p.permission.id) })}><Trash2 size={14} /></button>
                </div>
              ))}
            </div>
          ) : <p className="muted">No permission overrides</p>}
        </Panel>
      </div>

      <Panel title="Available Permissions">
        <div className="stack-lg">
          {permissions_by_dashboard.map((g) => (
            <div key={g.dashboard} className="stack">
              <div className="section-title">{g.dashboard}</div>
              <div className="grid-3">
                {g.modules.map((m) => (
                  <div key={m.module} className="well">
                    <div className="small"><strong>{m.module}</strong></div>
                    <div className="stack" style={{ marginTop: 8 }}>
                      {m.permissions.map((p) => (
                        <div key={p.id} className="row between">
                          <span className="small">{p.action_display}</span>
                          <span className="row-tight">
                            <button className="btn btn-ghost btn-icon" title="Grant" onClick={() => post({ action: 'grant_permission', permission_id: String(p.id) })}><Check size={13} /></button>
                            <button className="btn btn-ghost btn-icon" title="Deny" onClick={() => post({ action: 'deny_permission', permission_id: String(p.id) })}><X size={13} /></button>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
