/** templates/projects/delete_collaborator.html */
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Info, UserMinus, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { PageHeader, Panel, useToast } from '@/components/ui';
import { PageState, usePageData, type Collaborator } from '../shared';

interface Ctx { project: { id: number; title: string }; collaborator: Collaborator }

export default function CollaboratorDeletePage() {
  const { projectId, collaboratorId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const back = `/journal-selector/projects/${projectId}/`;
  const q = usePageData<Ctx>(['projects', 'collab-delete', projectId, collaboratorId],
    `/api/projects/${projectId}/collaborators/${collaboratorId}`, back, { action: 'delete' });
  if (!q.data) return <PageState q={q} />;
  const { project, collaborator: c } = q.data;

  const remove = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete(`/api/projects/${project.id}/collaborators/${c.id}`);
      toast.success(data.message);
      await qc.invalidateQueries({ queryKey: ['projects'] });
      navigate(back);
    } catch (e) {
      toast.error(errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <div className="proj-narrow" style={{ maxWidth: 640 }}>
      <PageHeader title="Remove Collaborator" />
      <Panel>
        <div className="center" style={{ marginBottom: 14 }}>
          <AlertTriangle size={32} style={{ color: 'var(--warn)', margin: '0 auto 8px' }} />
          <h2>Remove Collaborator</h2>
          <p className="muted">Are you sure you want to remove this collaborator from the project?</p>
        </div>
        <div className="well">
          <strong>{c.user.full_name}</strong>
          <dl className="kv" style={{ marginTop: 8 }}>
            <dt>Email:</dt><dd>{c.user.email}</dd>
            <dt>Role:</dt><dd>{c.role_display}</dd>
            <dt>Project:</dt><dd>{project.title}</dd>
            <dt>Joined:</dt><dd>{formatDate(c.joined_at)}</dd>
          </dl>
        </div>
        <div className="notice notice-warn center" style={{ marginTop: 14 }}>
          <Info size={13} style={{ display: 'inline', marginRight: 4 }} />
          This action cannot be undone. The user will lose access to this project immediately.
        </div>
        <div className="row" style={{ justifyContent: 'center', marginTop: 16 }}>
          <button className="btn btn-danger" onClick={remove} disabled={busy}><UserMinus size={14} /> Remove Collaborator</button>
          <Link to={back} className="btn btn-secondary"><X size={14} /> Cancel</Link>
        </div>
      </Panel>
    </div>
  );
}
