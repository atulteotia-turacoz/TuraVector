/** templates/projects/project_timeline.html — milestone formset (ProjectMilestoneFormSet). */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, File as FileIcon, Plus, Save, Trash2, Undo2, Workflow, X } from 'lucide-react';
import { api, authUrl, errorMessage } from '@/lib/api';
import { PageHeader, Spinner, useConfirm, useToast } from '@/components/ui';
import { fmtDay, PageState, StatusBadge, usePageData, type Choice } from '../shared';

interface Milestone {
  id: number; milestone_name: string; description: string | null; responsible_person_name: string | null;
  responsible_person_contact: string | null; start_date: string | null; end_date: string | null; tat_days: number | null;
  status: string; order: number; attachment_name: string | null;
}
interface TimelineData {
  project: { id: number; title: string; description: string; start_date: string | null; estimated_end_date: string | null; status: string; status_display: string };
  milestones: Milestone[]; milestone_statuses: Choice[]; can_edit: boolean;
}
interface Row {
  key: number; id: number | null; order: string; milestone_name: string; description: string;
  responsible_person_name: string; responsible_person_contact: string; start_date: string; end_date: string;
  status: string; tat: string; attachment_name: string | null; file: File | null; DELETE: boolean;
}

const toRow = (m: Milestone, key: number): Row => ({
  key, id: m.id, order: String(m.order), milestone_name: m.milestone_name, description: m.description ?? '',
  responsible_person_name: m.responsible_person_name ?? '', responsible_person_contact: m.responsible_person_contact ?? '',
  start_date: m.start_date ?? '', end_date: m.end_date ?? '', status: m.status, tat: m.tat_days ? String(m.tat_days) : '-',
  attachment_name: m.attachment_name, file: null, DELETE: false,
});

export default function ProjectTimelinePage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = usePageData<TimelineData>(['projects', 'timeline', projectId], `/api/projects/${projectId}/timeline`, '/journal-selector/projects/');
  const [rows, setRows] = useState<Row[]>([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const formIndex = useRef(0);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (!q.data) return;
    setRows(q.data.milestones.map((m, i) => toRow(m, i)));
    formIndex.current = q.data.milestones.length;
    setDirty(false);
  }, [q.data]);

  // Warn about unsaved changes
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = 'You have unsaved changes. Are you sure you want to leave?'; return e.returnValue; };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [dirty]);

  // Ctrl/Cmd+S saves
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); formRef.current?.requestSubmit(); }
    };
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, []);

  const update = useCallback((key: number, patch: Partial<Row>, recalc = false) => {
    setDirty(true);
    setRows((list) => list.map((r) => {
      if (r.key !== key) return r;
      const next = { ...r, ...patch };
      if (recalc && next.start_date && next.end_date) {
        const s = new Date(next.start_date); const e = new Date(next.end_date);
        if (e >= s) next.tat = String(Math.ceil(Math.abs(e.getTime() - s.getTime()) / 86400000));
        else { next.tat = 'Invalid'; toast.error('End date must be after start date'); }
      }
      return next;
    }));
  }, [toast]);

  if (!q.data) return <PageState q={q} />;
  const { project, milestone_statuses } = q.data;

  const addRow = () => {
    const idx = formIndex.current++;
    setDirty(true);
    setRows((list) => [...list, {
      key: Date.now() + idx, id: null, order: String(idx + 1), milestone_name: '', description: '', responsible_person_name: '',
      responsible_person_contact: '', start_date: '', end_date: '', status: 'not_started', tat: '-', attachment_name: null,
      file: null, DELETE: false,
    }]);
  };

  const removeRow = async (r: Row) => {
    const name = r.milestone_name || 'this milestone';
    if (!(await confirm({ title: 'Delete Milestone', message: `Are you sure you want to delete "${name}"? This action cannot be undone.`, confirmLabel: 'Delete', danger: true }))) return;
    if (r.id) {
      update(r.key, { DELETE: true });
      toast.success(`"${name}" marked for deletion`);
    } else {
      setRows((list) => list.filter((x) => x.key !== r.key));
      toast.success('Milestone removed');
    }
  };

  const undoRemove = (r: Row) => {
    update(r.key, { DELETE: false });
    toast.success(`"${r.milestone_name || 'milestone'}" restored`);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: string[] = [];
    rows.forEach((r, i) => { if (r.milestone_name.trim() === '') errs.push(`Milestone ${i + 1}: Name is required`); });
    rows.forEach((r, i) => {
      if (r.start_date && r.end_date && new Date(r.start_date) > new Date(r.end_date)) errs.push(`Milestone ${i + 1}: End date must be after start date`);
    });
    if (errs.length) { toast.error(errs.join('; ')); return; }

    setSaving(true);
    toast.info('Saving timeline...');
    const fd = new FormData();
    const payload = rows.map((r, i) => {
      if (r.file) fd.append(`attachment-${i}`, r.file);
      return {
        id: r.id, order: r.order, milestone_name: r.milestone_name, description: r.description,
        responsible_person_name: r.responsible_person_name, responsible_person_contact: r.responsible_person_contact,
        start_date: r.start_date, end_date: r.end_date, status: r.status, DELETE: r.DELETE, file_key: `attachment-${i}`,
      };
    });
    fd.append('milestones', JSON.stringify(payload));
    try {
      const { data } = await api.post(`/api/projects/${project.id}/timeline`, fd);
      toast.success(data.message);
      setDirty(false);
      await qc.invalidateQueries({ queryKey: ['projects'] });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader title={<span className="row-tight"><Workflow size={20} /> Project Timeline</span>}
        actions={<Link to={`/journal-selector/projects/${project.id}/`} className="btn btn-secondary"><ArrowLeft size={15} /> Back to Project</Link>} />

      <section className="panel" style={{ marginBottom: 18 }}>
        <div className="panel-body">
          <h3 className="serif" style={{ fontSize: 19 }}>{project.title}</h3>
          <p className="muted small">{project.description}</p>
          <div className="grid-3 small" style={{ marginTop: 12 }}>
            <div><strong>Start Date:</strong> {fmtDay(project.start_date, 'Not set')}</div>
            <div><strong>Estimated End:</strong> {fmtDay(project.estimated_end_date, 'Not set')}</div>
            <div><strong>Status:</strong> <StatusBadge value={project.status} label={project.status_display} /></div>
          </div>
        </div>
      </section>

      <form ref={formRef} onSubmit={submit}>
        <section className="panel">
          <div className="table-scroll">
            <table className="tbl proj-timeline-table">
              <thead>
                <tr>
                  <th style={{ width: 70 }}>#</th><th style={{ minWidth: 200 }}>Milestone</th><th style={{ minWidth: 160 }}>Responsible Person</th>
                  <th>Start Date</th><th>End Date</th><th>TAT</th><th style={{ minWidth: 130 }}>Status</th>
                  <th style={{ minWidth: 170 }}>Attachment</th><th>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const dis = r.DELETE;
                  return (
                    <tr key={r.key} className={r.DELETE ? 'proj-row-deleted' : ''}>
                      <td><input className="input" type="number" min={1} value={r.order} disabled={dis} onChange={(e) => update(r.key, { order: e.target.value })} /></td>
                      <td className="stacked">
                        <input className="input" placeholder="Milestone name" value={r.milestone_name} disabled={dis} onChange={(e) => update(r.key, { milestone_name: e.target.value })} />
                        <textarea className="input" rows={2} placeholder="Milestone description" value={r.description} disabled={dis} onChange={(e) => update(r.key, { description: e.target.value })} />
                      </td>
                      <td className="stacked">
                        <input className="input" placeholder="Name of responsible person" value={r.responsible_person_name} disabled={dis} onChange={(e) => update(r.key, { responsible_person_name: e.target.value })} />
                        <input className="input" placeholder="Contact details" value={r.responsible_person_contact} disabled={dis} onChange={(e) => update(r.key, { responsible_person_contact: e.target.value })} />
                      </td>
                      <td><input className="input" type="date" value={r.start_date} disabled={dis} onChange={(e) => update(r.key, { start_date: e.target.value }, true)} /></td>
                      <td><input className="input" type="date" value={r.end_date} disabled={dis} onChange={(e) => update(r.key, { end_date: e.target.value }, true)} /></td>
                      <td className="nowrap">{r.tat}</td>
                      <td>
                        <select className="input" value={r.status} disabled={dis} onChange={(e) => update(r.key, { status: e.target.value })}>
                          {milestone_statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                        </select>
                      </td>
                      <td>
                        {r.id && r.attachment_name && (
                          <div style={{ marginBottom: 6 }}>
                            <div className="tiny muted truncate" title={r.attachment_name}>{r.attachment_name}</div>
                            <a className="btn btn-secondary btn-sm" target="_blank" rel="noreferrer"
                              href={authUrl(`/api/projects/milestones/${r.id}/attachment`)}><FileIcon size={12} /> View File</a>
                          </div>
                        )}
                        <input className="input" type="file" disabled={dis} onChange={(e) => update(r.key, { file: e.target.files?.[0] ?? null })} />
                        {r.file && <div className="tiny" style={{ color: 'var(--accent)', marginTop: 4 }}>{r.file.name}</div>}
                      </td>
                      <td>
                        {r.DELETE
                          ? <button type="button" className="btn btn-secondary btn-icon" title="Undo Delete" onClick={() => undoRemove(r)}><Undo2 size={14} /></button>
                          : <button type="button" className="btn btn-ghost btn-icon" title="Delete Milestone" onClick={() => removeRow(r)}><Trash2 size={14} /></button>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="panel-foot between">
            <button type="button" className="btn btn-secondary" onClick={addRow}><Plus size={14} /> Add Milestone</button>
            <div className="row">
              <Link to={`/journal-selector/projects/${project.id}/`} className="btn btn-secondary"><X size={14} /> Cancel</Link>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? <><Spinner /> Saving...</> : <><Save size={14} /> Save Timeline</>}
              </button>
            </div>
          </div>
        </section>
      </form>
    </>
  );
}
