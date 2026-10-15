/** templates/projects/add_collaborator.html and edit_collaborator.html */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save, UserPen, UserPlus, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Field, PageHeader, Panel, SearchSelect, useToast } from '@/components/ui';
import { ErrorList, formError, PageState, ROLE_DESCRIPTIONS, usePageData, type Choice, type Collaborator, type FormErrorDetail, type UserOption } from '../shared';

interface AddCtx { project: { id: number; title: string; description_short: string }; users: UserOption[]; roles: Choice[]; default_role: string }
interface EditCtx { project: { id: number; title: string }; collaborator: Collaborator; user_option: UserOption; roles: Choice[] }

export default function CollaboratorFormPage() {
  const { projectId, collaboratorId } = useParams();
  const isEdit = !!collaboratorId;
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const back = `/journal-selector/projects/${projectId}/`;

  const addQ = usePageData<AddCtx>(['projects', 'collab-add', projectId], `/api/projects/${projectId}/collaborators/form`, back, undefined, !isEdit);
  const editQ = usePageData<EditCtx>(['projects', 'collab-edit', projectId, collaboratorId],
    `/api/projects/${projectId}/collaborators/${collaboratorId}`, back, { action: 'edit' }, isEdit);

  const [user, setUser] = useState<number | ''>('');
  const [role, setRole] = useState('contributor');
  const [errors, setErrors] = useState<FormErrorDetail | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (editQ.data) setRole(editQ.data.collaborator.role); }, [editQ.data]);
  useEffect(() => { if (addQ.data) setRole(addQ.data.default_role); }, [addQ.data]);

  const q = isEdit ? editQ : addQ;
  if (!q.data) return <PageState q={q} />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors(null);
    try {
      const { data } = isEdit
        ? await api.put(`/api/projects/${projectId}/collaborators/${collaboratorId}`, { role })
        : await api.post(`/api/projects/${projectId}/collaborators`, { user, role });
      toast.success(data.message);
      await qc.invalidateQueries({ queryKey: ['projects'] });
      navigate(back);
    } catch (err) {
      const fe = formError(err);
      if (fe) setErrors(fe); else toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const roles = (isEdit ? editQ.data?.roles : addQ.data?.roles) ?? [];
  return (
    <div className="proj-narrow" style={{ maxWidth: 760 }}>
      <PageHeader title={<span className="row-tight">{isEdit ? <UserPen size={20} /> : <UserPlus size={20} />} {isEdit ? 'Edit Collaborator' : 'Add Collaborator'}</span>}
        actions={<Link to={back} className="btn btn-secondary"><ArrowLeft size={15} /> Back to Project</Link>} />
      <Panel>
        <div className="well" style={{ marginBottom: 16 }}>
          {isEdit && editQ.data ? (
            <>
              <strong>{editQ.data.collaborator.user.full_name}</strong>
              <div className="small muted">{editQ.data.collaborator.user.email}</div>
              <div className="small">Project: {editQ.data.project.title}</div>
            </>
          ) : addQ.data && (
            <>
              <strong>{addQ.data.project.title}</strong>
              <p className="small muted">{addQ.data.project.description_short}</p>
            </>
          )}
        </div>
        <ErrorList detail={errors} />
        <form onSubmit={submit} className="stack" style={{ marginTop: errors ? 14 : 0 }}>
          {isEdit && editQ.data ? (
            <Field label="Collaborator" help="User cannot be changed when editing. To change the collaborator, remove this one and add a new collaborator.">
              <select className="input" disabled value={editQ.data.user_option.value}>
                <option value={editQ.data.user_option.value}>{editQ.data.user_option.label}</option>
              </select>
            </Field>
          ) : (
            <Field label="Select Collaborator" required help="Select the user you want to add as collaborator">
              <SearchSelect options={addQ.data?.users ?? []} value={user} onChange={(v) => setUser(v)}
                placeholder="-- Select User --" />
            </Field>
          )}
          <Field label="Role" required>
            <select className="input" value={role} onChange={(e) => setRole(e.target.value)}>
              {roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </Field>
          {ROLE_DESCRIPTIONS}
          <div className="row" style={{ marginTop: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {isEdit ? <><Save size={14} /> Update Role</> : <><UserPlus size={14} /> Add Collaborator</>}
            </button>
            <Link to={back} className="btn btn-secondary"><X size={14} /> Cancel</Link>
          </div>
        </form>
      </Panel>
    </div>
  );
}
