import { SITE_URL } from '@/components/Shell';
import { CardAccessPanel } from '@/components/CardAccessPanel';
import { Link, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ExternalLink, Lock, Pencil, Shield, UserCheck, UserX } from 'lucide-react';
import { api } from '@/lib/api';
import { Badge, ErrorNotice, Loading, PageHeader, Panel, Stat, useConfirm } from '@/components/ui';
import { formatDate, formatDateTime } from '@/lib/format';
import { ActiveBadge, DocStatus, truncate, useErrorToast, useFlash, usePageData, type ActionResult, type PermissionItem, type RoleItem, type UserRow } from '../shared';

interface ProfileData {
  viewed_user: UserRow;
  document_stats: { total: number; draft: number; review: number; approved: number;
    recent: { id: number; document_name: string; stage_status: number; created_at: string }[] };
  user_roles: { id: number; role: RoleItem }[];
  user_permissions: { id: number; is_granted: boolean; permission: PermissionItem }[];
}

export default function UserProfile() {
  const { userId } = useParams();
  const q = usePageData<ProfileData>(['profile', userId], `/api/users/${userId}/profile`);
  const confirm = useConfirm();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { viewed_user: u, document_stats: ds, user_roles, user_permissions } = q.data;
  const fullName = `${u.first_name} ${u.last_name}`.trim();
  const protectedAccount = u.is_superuser || u.username === 'admin';

  const toggle = async () => {
    const deactivate = u.is_active;
    if (!(await confirm({ message: `Are you sure you want to ${deactivate ? 'deactivate' : 'activate'} this user?`, danger: deactivate }))) return;
    try {
      const { data } = await api.post<ActionResult>(`/api/users/${u.id}/toggle-status`);
      flash(data.messages, data.message);
    } catch (e) { showError(e); }
    qc.invalidateQueries({ queryKey: ['users'] });
  };

  return (
    <div className="stack-lg">
      <PageHeader title={fullName} eyebrow="User Profile" subtitle={u.user_type_display}
        actions={<Link className="btn btn-secondary" to="/library/manage-users/"><ArrowLeft size={14} /> Back to All Users</Link>} />
      <div className="row-tight wrap">
        <ActiveBadge active={u.is_active} />
        {u.is_manager && <Badge tone="accent">Manager</Badge>}
        {u.is_superuser && <Badge tone="danger">Superuser</Badge>}
      </div>

      <div className="detail-grid">
        <div className="stack-lg">
          <Panel title="Personal Information">
            <dl className="kv">
              <dt>Email:</dt><dd>{u.email}</dd>
              <dt>Username:</dt><dd>{u.username}</dd>
              <dt>Phone:</dt><dd>{u.phone || 'Not provided'}</dd>
              <dt>Address:</dt><dd>{u.address || 'Not provided'}</dd>
              <dt>Joined:</dt><dd>{formatDate(u.date_joined)}</dd>
              <dt>Last Login:</dt><dd>{u.last_login ? formatDateTime(u.last_login) : 'Never'}</dd>
            </dl>
          </Panel>

          <div className="stat-grid">
            <Stat value={ds.total} label="Total Documents" />
            <Stat value={ds.draft} label="Draft" />
            <Stat value={ds.review} label="Under Review" />
            <Stat value={ds.approved} label="Approved" />
          </div>

          <Panel title="Recent Documents" flush>
            {ds.recent.length ? (
              <table className="tbl"><tbody>
                {ds.recent.map((doc) => (
                  <tr key={doc.id}>
                    <td><strong>{truncate(doc.document_name, 40)}</strong>
                      <div className="tiny muted">{formatDate(doc.created_at)} — {doc.stage_status <= 2 && <DocStatus status={doc.stage_status} variant="short" />}</div></td>
                    <td className="right"><a className="btn btn-ghost btn-icon" href={`${SITE_URL}/documents/document/${doc.id}/`} target="_blank" rel="noreferrer" title="Open in TuraVector"><ExternalLink size={14} /></a></td>
                  </tr>
                ))}
              </tbody></table>
            ) : <div className="empty small">No documents found</div>}
          </Panel>
        </div>

        <div className="stack-lg">
          <Panel title="Roles & Permissions">
            <div className="stack">
              {user_roles.length > 0 && (
                <div><div className="section-title small">Assigned Roles:</div>
                  <div className="row-tight wrap">{user_roles.map((ur) => <Badge key={ur.id} tone="accent">{ur.role.name}</Badge>)}</div></div>
              )}
              {user_permissions.length > 0 && (
                <div><div className="section-title small">Direct Permissions:</div>
                  <div className="row-tight wrap">{user_permissions.map((p) => (
                    <Badge key={p.id} tone={p.is_granted ? 'ok' : 'danger'}>{p.permission.module_display} - {p.permission.action_display}</Badge>
                  ))}</div></div>
              )}
              <Link className="btn btn-secondary btn-sm" to={`/library/user/${u.id}/permissions/`}><Shield size={14} /> Manage Permissions</Link>
            </div>
          </Panel>

          <CardAccessPanel userId={u.id} />

          <Panel title="Actions">
            <div className="stack">
              <Link className="btn btn-primary btn-block" to={`/library/user/${u.id}/edit/`}><Pencil size={14} /> Edit User</Link>
              <Link className="btn btn-secondary btn-block" to={`/library/user/${u.id}/permissions/`}><Shield size={14} /> Manage Permissions</Link>
              {!protectedAccount ? (
                u.is_active
                  ? <button className="btn btn-danger btn-block" onClick={toggle}><UserX size={14} /> Deactivate</button>
                  : <button className="btn btn-primary btn-block" onClick={toggle}><UserCheck size={14} /> Activate</button>
              ) : (
                <span className="btn btn-secondary btn-block" title="Admin accounts cannot be deactivated" aria-disabled="true"><Lock size={14} /> Protected Account</span>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
