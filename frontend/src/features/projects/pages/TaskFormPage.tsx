/** templates/projects/add_task.html and edit_task.html (ProjectTaskForm) */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Edit, Plus, Save, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Field, PageHeader, Panel, useToast } from '@/components/ui';
import { ErrorList, formError, PageState, PRIORITY_LEVELS, usePageData, type Choice, type FormErrorDetail, type Task, type UserOption } from '../shared';

interface Ctx {
  project: { id: number; title: string; description_short: string };
  users: UserOption[]; statuses: Choice[]; priorities: Choice[];
  initial?: { status: string; priority: string }; task?: Task;
}

export default function TaskFormPage() {
  const { projectId, taskId } = useParams();
  const isEdit = !!taskId;
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const back = `/journal-selector/projects/${projectId}/`;
  const q = usePageData<Ctx>(['projects', 'task-form', projectId, taskId ?? 'new'],
    isEdit ? `/api/projects/${projectId}/tasks/${taskId}` : `/api/projects/${projectId}/tasks/form`, back,
    isEdit ? { action: 'edit' } : undefined);

  const [v, setV] = useState({ title: '', description: '', status: 'todo', priority: 'medium', assigned_to: '', due_date: '' });
  const [errors, setErrors] = useState<FormErrorDetail | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const t = q.data?.task;
    if (t) setV({ title: t.title, description: t.description, status: t.status, priority: t.priority,
      assigned_to: t.assigned_to_id ? String(t.assigned_to_id) : '', due_date: t.due_date ?? '' });
  }, [q.data]);

  if (!q.data) return <PageState q={q} />;
  const ctx = q.data;
  const set = (k: keyof typeof v, val: string) => setV((s) => ({ ...s, [k]: val }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors(null);
    try {
      const { data } = isEdit
        ? await api.put(`/api/projects/${projectId}/tasks/${taskId}`, v)
        : await api.post(`/api/projects/${projectId}/tasks`, v);
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

  return (
    <div className="proj-narrow" style={{ maxWidth: 820 }}>
      <PageHeader title={<span className="row-tight">{isEdit ? <Edit size={20} /> : <Plus size={20} />} {isEdit ? 'Edit Task' : 'Add Task'}</span>}
        actions={<Link to={back} className="btn btn-secondary"><ArrowLeft size={15} /> Back to Project</Link>} />
      <Panel>
        <div className="well" style={{ marginBottom: 16 }}>
          {isEdit && ctx.task ? (
            <>
              <strong>{ctx.task.title}</strong>
              <div className="small">Project: {ctx.project.title}</div>
              <p className="small muted">{ctx.task.description || 'No description provided'}</p>
            </>
          ) : (
            <>
              <strong>{ctx.project.title}</strong>
              <p className="small muted">{ctx.project.description_short}</p>
            </>
          )}
        </div>
        <ErrorList detail={errors} />
        <form onSubmit={submit} className="form-grid" style={{ marginTop: errors ? 14 : 0 }}>
          <div className="span-2">
            <Field label="Task Title" required>
              <input className="input" required maxLength={255} placeholder="Enter task title" value={v.title} onChange={(e) => set('title', e.target.value)} />
            </Field>
          </div>
          <div className="span-2">
            <Field label="Description">
              <textarea className="input" rows={3} placeholder="Enter task description (optional)" value={v.description} onChange={(e) => set('description', e.target.value)} />
            </Field>
          </div>
          <Field label="Status" required>
            <select className="input" value={v.status} onChange={(e) => set('status', e.target.value)}>
              {ctx.statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
          <div>
            <Field label="Priority" required error={errors?.errors.priority?.[0]}>
              <select className="input" value={v.priority} onChange={(e) => set('priority', e.target.value)}>
                {ctx.priorities.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </Field>
            <div style={{ marginTop: 10 }}>{PRIORITY_LEVELS}</div>
          </div>
          <Field label="Assigned To" help="Select who should be assigned to this task">
            <select className="input" value={v.assigned_to} onChange={(e) => set('assigned_to', e.target.value)}>
              <option value="">-- Unassigned --</option>
              {ctx.users.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
            </select>
          </Field>
          <Field label="Due Date">
            <input className="input" type="date" value={v.due_date} onChange={(e) => set('due_date', e.target.value)} />
          </Field>
          <div className="span-2 row" style={{ marginTop: 6 }}>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {isEdit ? <><Save size={14} /> Update Task</> : <><Plus size={14} /> Add Task</>}
            </button>
            <Link to={back} className="btn btn-secondary"><X size={14} /> Cancel</Link>
          </div>
        </form>
      </Panel>
    </div>
  );
}
