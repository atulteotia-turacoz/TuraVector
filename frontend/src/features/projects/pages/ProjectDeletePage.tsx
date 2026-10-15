/** templates/projects/project_delete_confirm.html */
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, FileText, Folder, ListChecks, Signal, Trash2, Users } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { PageHeader, Panel, useConfirm, useToast } from '@/components/ui';
import { PageState, usePageData } from '../shared';

interface DeleteInfo {
  id: number; title: string; description: string; description_short: string; project_type_display: string;
  status_display: string; collaborator_count: number; task_count: number; document_count: number;
}

const plural = (n: number) => (n === 1 ? '' : 's');

export default function ProjectDeletePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const q = usePageData<DeleteInfo>(['projects', 'delete', projectId], `/api/projects/${projectId}/delete`, `/journal-selector/projects/${projectId}/`);
  if (!q.data) return <PageState q={q} />;
  const p = q.data;

  const doDelete = async () => {
    if (!(await confirm({ title: 'Delete Project', message: 'This action cannot be undone. Are you absolutely sure?', confirmLabel: 'Yes, Delete Project', danger: true }))) return;
    setBusy(true);
    try {
      const { data } = await api.delete(`/api/projects/${p.id}`);
      toast.success(data.message);
      await qc.invalidateQueries({ queryKey: ['projects'] });
      navigate('/journal-selector/projects/');
    } catch (e) {
      toast.error(errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <div className="proj-narrow" style={{ maxWidth: 680 }}>
      <PageHeader title="Delete Project" />
      <Panel>
        <div className="center" style={{ marginBottom: 16 }}>
          <AlertTriangle size={34} style={{ color: 'var(--danger)', margin: '0 auto 8px' }} />
          <h2>Delete Project Confirmation</h2>
          <p className="muted">Are you sure you want to delete this project?</p>
        </div>
        <div className="well">
          <h3>{p.title}</h3>
          {p.description && <p className="small muted" style={{ marginTop: 4 }}>{p.description_short}</p>}
          <ul className="stack small" style={{ listStyle: 'none', marginTop: 10 }}>
            <li className="row-tight"><Folder size={13} /> Type: {p.project_type_display}</li>
            <li className="row-tight"><Signal size={13} /> Status: {p.status_display}</li>
            <li className="row-tight"><Users size={13} /> {p.collaborator_count} collaborator{plural(p.collaborator_count)}</li>
            {p.task_count > 0 && <li className="row-tight"><ListChecks size={13} /> {p.task_count} task{plural(p.task_count)}</li>}
            {p.document_count > 0 && <li className="row-tight"><FileText size={13} /> {p.document_count} document{plural(p.document_count)}</li>}
          </ul>
        </div>
        <div className="notice notice-danger" style={{ marginTop: 14 }}>
          <div className="notice-title">This action will permanently delete:</div>
          <ul style={{ paddingLeft: 18 }}>
            <li>All project information and settings</li>
            <li>All associated tasks and milestones</li>
            <li>All uploaded documents</li>
            <li>All collaborator assignments</li>
          </ul>
        </div>
        <div className="row" style={{ marginTop: 18, justifyContent: 'center' }}>
          <button className="btn btn-danger" onClick={doDelete} disabled={busy}><Trash2 size={14} /> Yes, Delete Project</button>
          <Link to={`/journal-selector/projects/${p.id}/`} className="btn btn-secondary"><ArrowLeft size={14} /> Cancel</Link>
        </div>
      </Panel>
    </div>
  );
}
