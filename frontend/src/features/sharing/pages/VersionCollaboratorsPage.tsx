/** templates/documents/version_collaborators.html (documents/views_collaborators.py) */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { ArrowLeft, Edit, FileText, GitBranch, Info, Plus, Trash2, UserPlus, Users } from 'lucide-react';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Badge, Field, Modal, PageHeader, Panel, SearchSelect, StageStatus, useConfirm, useToast } from '@/components/ui';
import { PageState, usePageData, type Choice } from '../shared';

interface Sharing {
  id: number; user: { id: number; full_name: string; email: string }; shared_by: { id: number; full_name: string };
  shared_at: string; expires_at: string | null; permission_level: string; permission_level_display: string;
  role_required: { id: number; name: string } | null; can_share: boolean; can_download: boolean; can_annotate: boolean;
  can_delete_versions: boolean; notify_on_update: boolean; notes: string | null;
}
interface Ctx {
  version: { id: number; version_number: string; file_title_name: string; stage_status: number; stage_label: string | null };
  document: { id: number; document_name: string; document_number: string };
  collaborators: Sharing[]; available_users: { value: number; label: string }[];
  available_roles: { value: number; label: string }[]; permission_levels: Choice[];
}

const STAGE_TONES: Record<number, 'muted' | 'warn' | 'ok' | 'danger'> = { 0: 'muted', 1: 'warn', 2: 'ok', 3: 'danger' };
const apiError = (e: unknown) => (e as AxiosError<any>)?.response?.data?.error ?? (e as AxiosError<any>)?.response?.data?.detail ?? 'Request failed';

const FLAGS = [
  ['can_share', 'Can Share'], ['can_download', 'Can Download'], ['can_annotate', 'Can Annotate'],
  ['can_delete_versions', 'Can Delete Versions'], ['notify_on_update', 'Notify on Update'],
] as const;
type FlagKey = typeof FLAGS[number][0];

export default function VersionCollaboratorsPage() {
  const { versionId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = usePageData<Ctx>(['sharing', 'version-collaborators', versionId], `/api/sharing/versions/${versionId}/collaborators`,
    (err) => (err.response?.data?.document_id ? `/content-lab-management/document/${err.response.data.document_id}/` : '/content-lab-management/dashboard/'));

  const blankAdd = { user_id: '' as number | '', permission_level: 'view', role_id: '', expires_at: '', notes: '',
    can_share: false, can_download: true, can_annotate: true, can_delete_versions: false, notify_on_update: true };
  const [add, setAdd] = useState(blankAdd);
  const [edit, setEdit] = useState<(Omit<typeof blankAdd, 'user_id' | 'expires_at' | 'notes'> & { id: number }) | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (q.data) setAdd((a) => ({ ...a, permission_level: q.data!.permission_levels[0]?.value ?? 'view' })); }, [q.data]);

  const docId = q.data?.document.id;
  if (!q.data) return <PageState q={q} />;
  const { version, document, collaborators } = q.data;
  const reload = () => qc.invalidateQueries({ queryKey: ['sharing'] });

  const submitAdd = async (e: FormEvent) => {
    e.preventDefault();
    if (!add.user_id) { toast.error('Please select a user.'); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/api/sharing/versions/${version.id}/collaborators/add`, add);
      if (data.success) { toast.success(data.message); setAdd(blankAdd); await reload(); }
    } catch (err) {
      toast.error(`Error: ${apiError(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (s: Sharing) => {
    if (!(await confirm({ title: 'Remove collaborator', message: `Are you sure you want to remove ${s.user.full_name} as a collaborator from this version?`, confirmLabel: 'Remove', danger: true }))) return;
    try {
      const { data } = await api.post(`/api/sharing/versions/${version.id}/collaborators/remove/${s.id}`);
      if (data.success) { toast.success(data.message); await reload(); }
    } catch (err) {
      toast.error(`Error: ${apiError(err)}`);
    }
  };

  const openEdit = (s: Sharing) => setEdit({
    id: s.id, permission_level: s.permission_level, role_id: s.role_required ? String(s.role_required.id) : '',
    can_share: s.can_share, can_download: s.can_download, can_annotate: s.can_annotate,
    can_delete_versions: s.can_delete_versions, notify_on_update: s.notify_on_update,
  });

  const saveEdit = async () => {
    if (!edit) return;
    const { id, ...payload } = edit;
    try {
      const { data } = await api.post(`/api/sharing/versions/${version.id}/collaborators/update/${id}`, payload);
      if (data.success) { toast.success(data.message); setEdit(null); await reload(); }
    } catch (err) {
      toast.error(`Error: ${apiError(err)}`);
    }
  };

  return (
    <>
      <nav className="small muted" style={{ marginBottom: 8 }}>
        <Link to="/content-lab-management/dashboard/">Documents</Link> / <Link to={`/content-lab-management/document/${docId}/`}>{document.document_name}</Link> / <span>Version Collaborators</span>
      </nav>
      <PageHeader title="Manage Version Collaborators" />

      <section className="panel" style={{ marginBottom: 18 }}>
        <div className="panel-body grid-2">
          <div>
            <div className="row-tight"><FileText size={14} /> <strong>Document: {document.document_name}</strong></div>
            <div className="small" style={{ marginTop: 4 }}><strong>Document Number:</strong> {document.document_number}</div>
          </div>
          <div>
            <div className="row-tight"><GitBranch size={14} /> <strong>Version: {version.version_number}</strong></div>
            <div className="small" style={{ marginTop: 4 }}><strong>File:</strong> {version.file_title_name}</div>
            <div className="small row-tight" style={{ marginTop: 4 }}><strong>Status:</strong>
              {version.stage_label && <StageStatus label={version.stage_label} tone={STAGE_TONES[version.stage_status]} />}
            </div>
          </div>
        </div>
      </section>

      <Panel title={<span className="row-tight"><UserPlus size={15} /> Add New Collaborator to Version</span>}>
        <form onSubmit={submitAdd} className="stack">
          <div className="grid-4">
            <Field label="Select User" required>
              <SearchSelect options={q.data.available_users} value={add.user_id} onChange={(v) => setAdd({ ...add, user_id: v })} placeholder="-- Select User --" />
            </Field>
            <Field label="Permission Level" required>
              <select className="input" value={add.permission_level} onChange={(e) => setAdd({ ...add, permission_level: e.target.value })}>
                {q.data.permission_levels.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </Field>
            <Field label="Required Role (Optional)">
              <select className="input" value={add.role_id} onChange={(e) => setAdd({ ...add, role_id: e.target.value })}>
                <option value="">-- No Role Required --</option>
                {q.data.available_roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </Field>
            <Field label="Expires At">
              <input className="input" type="datetime-local" value={add.expires_at} onChange={(e) => setAdd({ ...add, expires_at: e.target.value })} />
            </Field>
          </div>
          <div>
            <div className="field-label">Permissions:</div>
            <div className="row wrap" style={{ gap: 18 }}>
              {FLAGS.map(([k, label]) => (
                <label key={k} className="check">
                  <input type="checkbox" checked={add[k as FlagKey]} onChange={(e) => setAdd({ ...add, [k]: e.target.checked })} /> {label}
                </label>
              ))}
            </div>
          </div>
          <Field label="Notes (Optional)">
            <textarea className="input" rows={2} placeholder="Add any notes about this version sharing..." value={add.notes} onChange={(e) => setAdd({ ...add, notes: e.target.value })} />
          </Field>
          <div className="row">
            <button type="submit" className="btn btn-primary" disabled={busy}><Plus size={14} /> Add Collaborator</button>
            <Link to={`/content-lab-management/document/${document.id}/`} className="btn btn-secondary"><ArrowLeft size={14} /> Back to Document</Link>
          </div>
        </form>
      </Panel>

      <h3 className="section-title row-tight"><Users size={13} /> Current Version Collaborators ({collaborators.length})</h3>
      {collaborators.length ? (
        <section className="panel">
          {collaborators.map((s) => (
            <div key={s.id} className="panel-body" style={{ borderBottom: '1px solid var(--hairline)' }}>
              <div className="grid-4" style={{ alignItems: 'start' }}>
                <div>
                  <strong>{s.user.full_name}</strong>
                  <div className="small muted">{s.user.email}</div>
                  <div className="tiny muted">Shared by {s.shared_by.full_name} on {formatDate(s.shared_at)}</div>
                </div>
                <div>
                  <Badge tone={s.permission_level === 'admin' ? 'danger' : s.permission_level === 'edit' ? 'warn' : 'accent'}>{s.permission_level_display}</Badge>
                  {s.role_required && <div className="tiny muted" style={{ marginTop: 4 }}>Requires: {s.role_required.name}</div>}
                </div>
                <div>
                  <div className="sh-perm-badges">
                    {s.can_share && <Badge>Can Share</Badge>}
                    {s.can_download && <Badge>Can Download</Badge>}
                    {s.can_annotate && <Badge>Can Annotate</Badge>}
                    {s.can_delete_versions && <Badge tone="warn">Can Delete</Badge>}
                  </div>
                  {s.expires_at && <div className="tiny" style={{ color: 'var(--danger)', marginTop: 4 }}>Expires: {formatDate(s.expires_at)}</div>}
                </div>
                <div className="row-tight" style={{ justifyContent: 'flex-end' }}>
                  <button className="btn btn-secondary btn-sm" onClick={() => openEdit(s)}><Edit size={13} /> Edit</button>
                  <button className="btn btn-danger btn-sm" onClick={() => remove(s)}><Trash2 size={13} /> Remove</button>
                </div>
              </div>
              {s.notes && <div className="tiny muted" style={{ marginTop: 8 }}><em>Notes: {s.notes}</em></div>}
            </div>
          ))}
        </section>
      ) : (
        <div className="notice notice-accent"><Info size={13} style={{ display: 'inline', marginRight: 4 }} /> No collaborators have been added to this document version yet.</div>
      )}

      <Modal open={!!edit} onClose={() => setEdit(null)} title="Edit Version Collaborator Permissions"
        footer={<>
          <button className="btn btn-secondary" onClick={() => setEdit(null)}>Cancel</button>
          <button className="btn btn-primary" onClick={saveEdit}>Save Changes</button>
        </>}>
        {edit && (
          <div className="stack">
            <Field label="Permission Level">
              <select className="input" value={edit.permission_level} onChange={(e) => setEdit({ ...edit, permission_level: e.target.value })}>
                {q.data.permission_levels.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </Field>
            <Field label="Required Role">
              <select className="input" value={edit.role_id} onChange={(e) => setEdit({ ...edit, role_id: e.target.value })}>
                <option value="">-- No Role Required --</option>
                {q.data.available_roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </Field>
            <div>
              <div className="field-label">Permissions:</div>
              <div className="stack">
                {FLAGS.map(([k, label]) => (
                  <label key={k} className="check">
                    <input type="checkbox" checked={edit[k as FlagKey]} onChange={(e) => setEdit({ ...edit, [k]: e.target.checked })} /> {label}
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
