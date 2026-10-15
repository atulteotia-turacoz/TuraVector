/** templates/projects/project_detail.html */
import { Link, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, BookOpen, Building2, Calendar, CalendarCheck, CalendarPlus, DollarSign, Download, Edit, FileText, Flag,
  FlagTriangleRight, FlaskConical, HeartPulse, MoreHorizontal, Play, Plus, Trash2, Upload, User, UserRound, Users, Workflow,
} from 'lucide-react';
import { api, downloadFile, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Badge, PageHeader, Panel, Stat, useConfirm, useToast } from '@/components/ui';
import { Avatar, fmtDay, PageState, StatusBadge, usePageData, type ProjectDetail } from '../shared';

function SectionEmpty({ title, text, action }: { title: string; text: string; action?: React.ReactNode }) {
  return <div className="proj-section-empty"><h5>{title}</h5><p className="small">{text}</p>{action && <div style={{ marginTop: 10 }}>{action}</div>}</div>;
}

export default function ProjectDetailPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = usePageData<ProjectDetail>(['projects', 'detail', projectId], `/api/projects/${projectId}`, '/journal-selector/projects/');
  if (!q.data) return <PageState q={q} />;
  const p = q.data;
  const canWork = p.is_owner || p.is_collaborator;
  const base = `/journal-selector/projects/${p.id}`;

  const deleteDoc = async (docId: number) => {
    if (!(await confirm({ title: 'Delete document', message: 'Are you sure you want to delete this document?', confirmLabel: 'Delete', danger: true }))) return;
    try {
      const { data } = await api.delete(`/api/projects/${p.id}/documents/${docId}`);
      toast.success(data.message);
    } catch (e) {
      toast.error(errorMessage(e));
    }
    await qc.invalidateQueries({ queryKey: ['projects'] });
  };

  const download = async (docId: number, name: string) => {
    try { await downloadFile(`/api/projects/${p.id}/documents/${docId}/download`, undefined, name); }
    catch (e) { toast.error(errorMessage(e, 'File not found')); }
  };

  const typeLabel = p.project_type === 'other' && p.project_type_other ? p.project_type_other : p.project_type_display;
  const clientLabel = p.client_type === 'other' && p.client_other ? p.client_other : p.client_type_display;
  const taLabel = p.therapeutic_area === 'others' && p.therapeutic_area_other ? p.therapeutic_area_other : p.therapeutic_area_display;

  return (
    <>
      <PageHeader
        eyebrow={<StatusBadge value={p.status} label={p.status_display} />}
        title={p.title}
        subtitle={p.description}
        actions={<>
          <Link to={`${base}/timeline/`} className="btn btn-primary"><Workflow size={15} /> Timeline</Link>
          {p.is_owner && <Link to={`${base}/edit/`} className="btn btn-secondary"><Edit size={15} /> Edit</Link>}
          <Link to="/journal-selector/projects/" className="btn btn-secondary"><ArrowLeft size={15} /> Back to Projects</Link>
        </>}
      />

      <section className="panel">
        <div className="panel-body">
          <div className="proj-info-grid" style={{ marginTop: 0 }}>
            <div><User size={14} /><span><strong>Owner:</strong> {p.owner.full_name}</span></div>
            <div><CalendarPlus size={14} /><span><strong>Created:</strong> {formatDate(p.created_at)}</span></div>
            {p.project_type && <div><FileText size={14} /><span><strong>Project Type:</strong> {typeLabel}</span></div>}
            {p.client_type && <div><Building2 size={14} /><span><strong>Client:</strong> {clientLabel}</span></div>}
            {p.client_poc_name && <div><UserRound size={14} /><span><strong>Client POC:</strong> {p.client_poc_name}{p.client_poc_email && ` (${p.client_poc_email})`}</span></div>}
            {p.therapeutic_area && <div><HeartPulse size={14} /><span><strong>Therapeutic Area:</strong> {taLabel}{p.sub_therapy_area && ` - ${p.sub_therapy_area}`}</span></div>}
            {p.journal_name && <div><BookOpen size={14} /><span><strong>Journal:</strong> {p.journal_name}</span></div>}
            {p.start_date && <div><Play size={14} /><span><strong>Start Date:</strong> {fmtDay(p.start_date)}</span></div>}
            {p.estimated_end_date && <div><CalendarCheck size={14} /><span><strong>Estimated End Date:</strong> {fmtDay(p.estimated_end_date)}</span></div>}
            {p.actual_end_date && <div><FlagTriangleRight size={14} /><span><strong>Actual End Date:</strong> {fmtDay(p.actual_end_date)}</span></div>}
            {p.deadline && <div><Flag size={14} /><span><strong>Deadline:</strong> {fmtDay(p.deadline)}</span></div>}
            {p.research_field && <div><FlaskConical size={14} /><span><strong>Field:</strong> {p.research_field}</span></div>}
            {p.budget && Number(p.budget) !== 0 && <div><DollarSign size={14} /><span><strong>Budget:</strong> ${p.budget}</span></div>}
          </div>
          {p.keywords_list.length > 0 && (
            <div className="row wrap" style={{ marginTop: 14, gap: 6 }}>
              <strong className="small">Keywords:</strong>
              {p.keywords_list.map((k) => <Badge key={k}>{k}</Badge>)}
            </div>
          )}
        </div>
      </section>

      <div className="stat-grid" style={{ margin: '20px 0' }}>
        <Stat value={p.tasks.length} label="Tasks" />
        <Stat value={p.collaborators.length} label="Collaborators" />
        <Stat value={p.documents.length} label="Documents" />
        <Stat value={`${p.progress_percentage}%`} label="Progress" />
      </div>

      <div className="grid-2">
        {p.has_authors && (
          <Panel title="Authors">
            {p.authors.length ? p.authors.map((a) => (
              <div key={a.id} className="proj-person">
                <Avatar text={a.name.slice(0, 2)} />
                <div className="grow">
                  <div>{a.name} {a.author_type === 'corresponding' && <Badge tone="accent">Corresponding</Badge>}</div>
                  <div className="small muted">{a.affiliation}</div>
                  <div className="small muted">{a.email}</div>
                </div>
              </div>
            )) : <SectionEmpty title="No Authors Added Yet" text="Authors will appear here once added to the project." />}
          </Panel>
        )}

        <Panel title="Collaborators" actions={<>
          <Link to={`${base}/collaborators/`} className="btn btn-secondary btn-sm"><Users size={13} /> View All</Link>
          {p.is_owner && <Link to={`${base}/collaborators/add/`} className="btn btn-primary btn-sm"><Plus size={13} /> Add</Link>}
        </>}>
          {p.collaborators.length ? (
            <>
              {p.collaborators.slice(0, 3).map((c) => (
                <div key={c.id} className="proj-person">
                  <Avatar text={c.user.initials} />
                  <div className="grow">
                    <div>{c.user.full_name}</div>
                    <div className="small muted">{c.role_display}</div>
                  </div>
                  {p.is_owner && (
                    <div className="actions">
                      <Link to={`${base}/collaborators/${c.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit Role"><Edit size={14} /></Link>
                      <Link to={`${base}/collaborators/${c.id}/delete/`} className="btn btn-ghost btn-icon" title="Remove"><Trash2 size={14} /></Link>
                    </div>
                  )}
                </div>
              ))}
              {p.collaborators.length > 3 && (
                <div className="center" style={{ marginTop: 10 }}>
                  <Link to={`${base}/collaborators/`} className="small muted row-tight" style={{ justifyContent: 'center' }}>
                    <MoreHorizontal size={14} /> And {p.collaborators.length - 3} more...
                  </Link>
                </div>
              )}
            </>
          ) : (
            <SectionEmpty title="No Collaborators Yet" text="Add team members to collaborate on this project."
              action={p.is_owner && <Link to={`${base}/collaborators/add/`} className="btn btn-primary btn-sm"><Plus size={13} /> Add First Collaborator</Link>} />
          )}
        </Panel>

        <Panel title="Tasks" actions={canWork && <Link to={`${base}/tasks/add/`} className="btn btn-primary btn-sm"><Plus size={13} /> Add Task</Link>}>
          {p.tasks.length ? p.tasks.map((t) => (
            <div key={t.id} className="proj-task">
              <div className="between">
                <strong>{t.title}</strong>
                {canWork && (
                  <div className="actions">
                    <Link to={`${base}/tasks/${t.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit Task"><Edit size={14} /></Link>
                    <Link to={`${base}/tasks/${t.id}/delete/`} className="btn btn-ghost btn-icon" title="Delete Task"><Trash2 size={14} /></Link>
                  </div>
                )}
              </div>
              <div className="proj-task-meta">
                <StatusBadge value={t.status} label={t.status_display} />
                <StatusBadge value={t.priority} label={t.priority_display} />
                {t.assigned_to && <span><User size={12} /> {t.assigned_to.full_name}</span>}
                {t.due_date && <span><Calendar size={12} /> {fmtDay(t.due_date)}</span>}
              </div>
              {t.description && <p className="small muted" style={{ marginTop: 6 }}>{t.description_short}</p>}
            </div>
          )) : (
            <SectionEmpty title="No Tasks Yet" text="Create tasks to organize your project work."
              action={canWork && <Link to={`${base}/tasks/add/`} className="btn btn-primary btn-sm"><Plus size={13} /> Add First Task</Link>} />
          )}
        </Panel>
      </div>

      <div style={{ marginTop: 20 }}>
        <Panel flush title="Documents" actions={canWork && <Link to={`${base}/upload-document/`} className="btn btn-primary btn-sm"><Upload size={13} /> Upload Document</Link>}>
          {p.documents.length ? (
            <div className="table-scroll">
              <table className="tbl">
                <thead><tr><th>Title</th><th>Description</th><th>Uploaded By</th><th>Upload Date</th><th>Actions</th></tr></thead>
                <tbody>
                  {p.documents.map((d) => (
                    <tr key={d.id}>
                      <td>{d.title}</td>
                      <td>{d.description_short}</td>
                      <td>{d.uploaded_by.full_name}</td>
                      <td>{formatDate(d.uploaded_at)}</td>
                      <td>
                        <div className="actions">
                          <button className="btn btn-secondary btn-sm" onClick={() => download(d.id, d.file_name)}><Download size={13} /> Download</button>
                          {d.can_delete && <button className="btn btn-ghost btn-icon" title="Delete" onClick={() => deleteDoc(d.id)}><Trash2 size={14} /></button>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <SectionEmpty title="No Documents Yet" text="Upload documents related to this project."
              action={canWork && <Link to={`${base}/upload-document/`} className="btn btn-primary btn-sm"><Upload size={13} /> Upload First Document</Link>} />
          )}
        </Panel>
      </div>
    </>
  );
}
