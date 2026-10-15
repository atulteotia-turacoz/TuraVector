/** templates/projects/delete_task.html */
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, Trash2, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { PageHeader, Panel, useToast } from '@/components/ui';
import { fmtDay, PageState, StatusBadge, usePageData, type Task } from '../shared';

interface Ctx { project: { id: number; title: string }; task: Task }

export default function TaskDeletePage() {
  const { projectId, taskId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const back = `/journal-selector/projects/${projectId}/`;
  const q = usePageData<Ctx>(['projects', 'task-delete', projectId, taskId], `/api/projects/${projectId}/tasks/${taskId}`, back, { action: 'delete' });
  if (!q.data) return <PageState q={q} />;
  const { project, task: t } = q.data;

  const remove = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete(`/api/projects/${project.id}/tasks/${t.id}`);
      toast.success(data.message);
      await qc.invalidateQueries({ queryKey: ['projects'] });
      navigate(back);
    } catch (e) {
      toast.error(errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <div className="proj-narrow" style={{ maxWidth: 760 }}>
      <PageHeader title={<span className="row-tight"><Trash2 size={20} /> Delete Task</span>}
        actions={<Link to={back} className="btn btn-secondary"><ArrowLeft size={15} /> Back to Project</Link>} />
      <Panel>
        <div className="well">
          <strong>{t.title}</strong>
          <div className="small">Project: {project.title}</div>
          {t.description && <p className="small muted">{t.description}</p>}
        </div>
        <dl className="kv" style={{ margin: '16px 0' }}>
          <dt>Status:</dt><dd><StatusBadge value={t.status} label={t.status_display} /></dd>
          <dt>Priority:</dt><dd><StatusBadge value={t.priority} label={t.priority_display} /></dd>
          {t.assigned_to && <><dt>Assigned To:</dt><dd>{t.assigned_to.full_name}</dd></>}
          {t.due_date && <><dt>Due Date:</dt><dd>{fmtDay(t.due_date)}</dd></>}
          <dt>Created:</dt><dd>{formatDateTime(t.created_at)}</dd>
        </dl>
        <div className="notice notice-danger">
          <AlertTriangle size={13} style={{ display: 'inline', marginRight: 4 }} />
          Are you sure you want to delete this task? This action cannot be undone.
        </div>
        <div className="row" style={{ marginTop: 16 }}>
          <button className="btn btn-danger" onClick={remove} disabled={busy}><Trash2 size={14} /> Yes, Delete Task</button>
          <Link to={back} className="btn btn-secondary"><X size={14} /> Cancel</Link>
        </div>
      </Panel>
    </div>
  );
}
