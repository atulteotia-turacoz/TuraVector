/** templates/projects/project_collaborators.html */
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Calendar, CalendarPlus, Crown, Edit, Trash2, UserPlus, Users } from 'lucide-react';
import { formatDate } from '@/lib/format';
import { Badge, Empty, PageHeader } from '@/components/ui';
import { Avatar, PageState, StatusBadge, usePageData, type Collaborator, type UserBrief } from '../shared';

interface Resp {
  project: { id: number; title: string; description_short: string; owner: UserBrief; created_at: string };
  collaborators: Collaborator[]; can_manage: boolean;
}

export default function ProjectCollaboratorsPage() {
  const { projectId } = useParams();
  const q = usePageData<Resp>(['projects', 'project-collaborators', projectId], `/api/projects/${projectId}/collaborators`, '/journal-selector/projects/');
  if (!q.data) return <PageState q={q} />;
  const { project, collaborators, can_manage } = q.data;
  const base = `/journal-selector/projects/${project.id}`;

  return (
    <>
      <PageHeader title={<span className="row-tight"><Users size={20} /> Project Collaborators</span>}
        actions={<>
          {can_manage && <Link to={`${base}/collaborators/add/`} className="btn btn-primary"><UserPlus size={15} /> Add Collaborator</Link>}
          <Link to={`${base}/`} className="btn btn-secondary"><ArrowLeft size={15} /> Back to Project</Link>
        </>} />

      <section className="panel">
        <div className="panel-body">
          <h3 className="serif" style={{ fontSize: 19 }}>{project.title}</h3>
          <p className="small muted">{project.description_short}</p>

          <div className="proj-person" style={{ marginTop: 10 }}>
            <Avatar text={project.owner.initials} />
            <div className="grow">
              <div>{project.owner.full_name}</div>
              <div className="small muted">{project.owner.email}</div>
              <div className="tiny muted row-tight"><Calendar size={11} /> Owner since {formatDate(project.created_at)}</div>
            </div>
            <Badge tone="accent"><Crown size={11} style={{ display: 'inline' }} /> Project Owner</Badge>
          </div>

          {collaborators.length ? (
            <>
              <h4 className="section-title row-tight"><Users size={13} /> Collaborators ({collaborators.length})</h4>
              {collaborators.map((c) => (
                <div key={c.id} className="proj-person">
                  <Avatar text={c.user.initials} />
                  <div className="grow">
                    <div>{c.user.full_name}</div>
                    <div className="small muted">{c.user.email}</div>
                    <div className="tiny muted row" style={{ gap: 10, marginTop: 3 }}>
                      <span className="row-tight"><CalendarPlus size={11} /> Joined {formatDate(c.joined_at)}</span>
                      <StatusBadge value={c.role} label={c.role_display} />
                    </div>
                  </div>
                  {can_manage && (
                    <div className="actions">
                      <Link to={`${base}/collaborators/${c.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit Role"><Edit size={14} /></Link>
                      <Link to={`${base}/collaborators/${c.id}/delete/`} className="btn btn-ghost btn-icon" title="Remove Collaborator"><Trash2 size={14} /></Link>
                    </div>
                  )}
                </div>
              ))}
            </>
          ) : (
            <Empty title="No Collaborators Yet"
              action={can_manage && <Link to={`${base}/collaborators/add/`} className="btn btn-primary"><UserPlus size={15} /> Add First Collaborator</Link>}>
              This project doesn't have any collaborators yet.
            </Empty>
          )}
        </div>
      </section>
    </>
  );
}
