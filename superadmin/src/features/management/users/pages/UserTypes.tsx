/** manage_user_types.html, create_user_type.html, edit_user_type.html */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, Pencil, Plus, Power, Save, Trash2, X } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '../../auth';
import { Badge, DataTable, Empty, ErrorNotice, Field, Loading, Modal, PageHeader, Panel, useToast, type Column } from '@/components/ui';
import { formatDate, formatDateTime } from '@/lib/format';
import { truncate, useErrorToast, useFlash, usePageData, type ActionResult, type UserTypeItem } from '../shared';

const CODE_RE = /^[a-z0-9_]+$/;

export function UserTypesList() {
  const { user } = useAuth();
  const q = usePageData<{ user_types: UserTypeItem[] }>(['user-types'], '/api/users/user-types');
  const qc = useQueryClient();
  const toast = useToast();
  const flash = useFlash();
  const showError = useErrorToast();
  const [deleting, setDeleting] = useState<UserTypeItem | null>(null);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;

  const toggle = async (t: UserTypeItem) => {
    try {
      const { data } = await api.post<ActionResult>(`/api/users/user-types/${t.id}/toggle-status`);
      toast.success(data.message || '');
      qc.invalidateQueries({ queryKey: ['users', 'user-types'] });
    } catch (err) {
      const m = (err as any)?.response?.data?.detail;
      toast.error(typeof m === 'string' ? m : 'An error occurred while updating the user type status.');
    }
  };
  const doDelete = async () => {
    if (!deleting) return;
    try {
      const { data } = await api.post<ActionResult>(`/api/users/user-types/${deleting.id}/delete`);
      flash(data.messages, data.message);
    } catch (err) { showError(err); }
    setDeleting(null);
    qc.invalidateQueries({ queryKey: ['users'] });
  };

  const columns: Column<UserTypeItem>[] = [
    { key: 'name', header: 'Name', render: (t) => <strong>{t.name}</strong> },
    { key: 'code', header: 'Code', render: (t) => <code className="mono small">{t.code}</code> },
    { key: 'description', header: 'Description', render: (t) => (t.description ? truncate(t.description, 50) : <span className="muted">No description</span>) },
    { key: 'is_active', header: 'Status', value: (t) => (t.is_active ? 'Active' : 'Inactive'),
      render: (t) => (t.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Inactive</Badge>) },
    { key: 'is_system', header: 'Type', value: (t) => (t.is_system ? 'System' : 'Custom'),
      render: (t) => (t.is_system ? <Badge tone="warn">System</Badge> : <Badge>Custom</Badge>) },
    { key: 'user_count', header: 'Users Count', render: (t) => `${t.user_count ?? 0} users` },
    { key: 'created_at', header: 'Created', value: (t) => t.created_at || '', render: (t) => formatDate(t.created_at) },
    { key: 'actions', header: '', sortable: false, render: (t) => (
      <div className="row-tight nowrap">
        <Link className="btn btn-ghost btn-icon" title="Edit User Type" to={`/library/user-type/${t.id}/edit/`}><Pencil size={14} /></Link>
        {(!t.is_system || user?.is_superuser) && (
          <button className="btn btn-ghost btn-icon" title={`${t.is_active ? 'Deactivate' : 'Activate'} User Type`} onClick={() => toggle(t)}><Power size={14} /></button>
        )}
        {!t.is_system && (
          <button className="btn btn-ghost btn-icon" title="Delete User Type" disabled={(t.user_count ?? 0) > 0} onClick={() => setDeleting(t)}><Trash2 size={14} /></button>
        )}
      </div>
    ) },
  ];

  return (
    <div className="stack-lg">
      <PageHeader title="User Type Management" eyebrow="Manage User Types" subtitle="Create and manage user types for the system"
        actions={<Link className="btn btn-primary" to="/library/user-type/create/"><Plus size={14} /> Create New User Type</Link>} />
      <Panel title="User Types">
        {q.data.user_types.length ? (
          <DataTable rows={q.data.user_types} columns={columns} rowKey={(t) => t.id} pageSize={10} />
        ) : (
          <Empty title="No User Types Found" action={<Link className="btn btn-primary" to="/library/user-type/create/"><Plus size={14} /> Create User Type</Link>}>
            Create your first user type to get started.
          </Empty>
        )}
      </Panel>
      <Modal open={!!deleting} onClose={() => setDeleting(null)} title={<span className="row-tight"><AlertTriangle size={16} /> Confirm Deletion</span>}
        footer={<>
          <button className="btn btn-secondary" onClick={() => setDeleting(null)}>Cancel</button>
          <button className="btn btn-danger" onClick={doDelete}><Trash2 size={14} /> Delete User Type</button>
        </>}>
        <p>Are you sure you want to delete the user type "<strong>{deleting?.name}</strong>"?</p>
        <div className="notice notice-warn">This action cannot be undone.</div>
      </Modal>
    </div>
  );
}

function TypeForm({ initial, disabled, onSubmit, submitLabel, autoCode }: {
  initial: { name: string; code: string; description: string; is_active: boolean };
  disabled?: boolean;
  onSubmit?: (v: { name: string; code: string; description: string; is_active: boolean }) => Promise<void>;
  submitLabel: string; autoCode?: boolean;
}) {
  const toast = useToast();
  const [v, setV] = useState(initial);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!onSubmit) return;
    const name = v.name.trim();
    const code = v.code.trim();
    if (!name) { toast.error('Please enter a user type name.'); return; }
    if (!code) { toast.error('Please enter a user type code.'); return; }
    if (!CODE_RE.test(code)) { toast.error('Code can only contain lowercase letters, numbers, and underscores.'); return; }
    setBusy(true);
    try { await onSubmit(v); } finally { setBusy(false); }
  };
  return (
    <form className="stack" onSubmit={submit}>
      <Field label="Name" required help="The display name for this user type (up to 50 characters)">
        <input className="input" maxLength={50} required disabled={disabled} placeholder="e.g., Senior Researcher" value={v.name}
          onChange={(e) => {
            const name = e.target.value;
            const next = { ...v, name };
            if (autoCode) next.code = name.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, '_').substring(0, 20);
            setV(next);
          }} />
      </Field>
      <Field label="Code" required help="Internal code for the user type (lowercase, no spaces, up to 20 characters)">
        <input className="input mono" maxLength={20} required disabled={disabled} placeholder="e.g., senior_researcher" value={v.code}
          onChange={(e) => setV({ ...v, code: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') })} />
      </Field>
      <Field label="Description" help="Optional description of the user type's role and responsibilities">
        <textarea className="input" rows={3} disabled={disabled} placeholder="Describe what this user type can do and their responsibilities..."
          value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} />
      </Field>
      <label className="check">
        <input type="checkbox" disabled={disabled} checked={v.is_active} onChange={(e) => setV({ ...v, is_active: e.target.checked })} />
        <span>Active Status<span className="field-help">Active user types are available for selection when creating users</span></span>
      </label>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <Link className="btn btn-secondary" to="/library/user-types/"><X size={14} /> Cancel</Link>
        {onSubmit && <button className="btn btn-primary" type="submit" disabled={busy}><Save size={14} /> {busy ? (submitLabel.startsWith('Create') ? 'Creating...' : 'Updating...') : submitLabel}</button>}
      </div>
    </form>
  );
}

export function UserTypeCreate() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();
  useEffect(() => {
    if (user && !(user.is_superuser || user.is_manager_like)) {
      toast.error('You do not have permission to create user types.');
      navigate('/library/user-types/', { replace: true });
    }
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="stack-lg">
      <div className="small muted"><Link className="act" to="/library/user-types/">User Types</Link> / Create New</div>
      <PageHeader title="Create New User Type" subtitle="Define a new user type for the system"
        actions={<Link className="btn btn-secondary" to="/library/user-types/"><ArrowLeft size={14} /> Back to User Types</Link>} />
      <div className="detail-grid">
        <Panel title="User Type Information">
          <TypeForm autoCode submitLabel="Create User Type" initial={{ name: '', code: '', description: '', is_active: true }}
            onSubmit={async (v) => {
              try {
                const { data } = await api.post<ActionResult>('/api/users/user-types', v);
                flash(data.messages, data.message);
                qc.invalidateQueries({ queryKey: ['users'] });
                navigate('/library/user-types/');
              } catch (err) { showError(err); }
            }} />
        </Panel>
        <Panel title="Guidelines">
          <ul className="users-list small">
            <li><strong>Name:</strong> Choose a clear, descriptive name for the user type</li>
            <li><strong>Code:</strong> Use lowercase letters, numbers, and underscores only</li>
            <li><strong>Description:</strong> Briefly explain the role and permissions of this user type</li>
            <li><strong>Status:</strong> Only active user types will be available when creating new users</li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}

export function UserTypeEdit() {
  const { userTypeId } = useParams();
  const { user } = useAuth();
  const q = usePageData<{ user_type: UserTypeItem }>(['user-type', userTypeId], `/api/users/user-types/${userTypeId}`);
  const navigate = useNavigate();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const t = q.data.user_type;
  const locked = t.is_system && !user?.is_superuser;
  return (
    <div className="stack-lg">
      <div className="small muted"><Link className="act" to="/library/user-types/">User Types</Link> / Edit: {t.name}</div>
      <PageHeader title="Edit User Type" subtitle="Modify user type settings and permissions"
        actions={<Link className="btn btn-secondary" to="/library/user-types/"><ArrowLeft size={14} /> Back to User Types</Link>} />
      {t.is_system && (
        <div className="notice notice-warn">
          <div className="notice-title">System User Type</div>
          This is a system user type. {locked ? 'Only superusers can modify system user types.' : 'Please be careful when making changes as this may affect system functionality.'}
        </div>
      )}
      <div className="detail-grid">
        <Panel title={`Edit User Type: ${t.name}`} actions={<span className="tiny muted">Created: {formatDate(t.created_at)} | Users: {t.user_count ?? 0}</span>}>
          {(t.user_count ?? 0) > 0 && (
            <div className="notice notice-accent" style={{ marginBottom: 16 }}>
              <strong>Usage Information:</strong> This user type is currently assigned to {t.user_count} user(s). Changes will affect all users with this type.
            </div>
          )}
          <TypeForm disabled={locked} submitLabel="Update User Type"
            initial={{ name: t.name, code: t.code, description: t.description, is_active: t.is_active }}
            onSubmit={locked ? undefined : async (v) => {
              try {
                const { data } = await api.post<ActionResult>(`/api/users/user-types/${t.id}`, v);
                flash(data.messages, data.message);
                qc.invalidateQueries({ queryKey: ['users'] });
                navigate('/library/user-types/');
              } catch (err) { showError(err); }
            }} />
        </Panel>
        <Panel title="Audit Information">
          <dl className="kv users-kv-tight">
            <dt>Created</dt><dd><strong>{formatDateTime(t.created_at)}</strong></dd>
            <dt>Last Modified</dt><dd><strong>{formatDateTime(t.updated_at)}</strong></dd>
          </dl>
        </Panel>
      </div>
    </div>
  );
}
