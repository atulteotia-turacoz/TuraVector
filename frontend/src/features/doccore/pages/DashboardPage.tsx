/** content_lab_dashboard_view / home_view — renders user_home.html or teacher_home.html (managers are redirected). */
import { ApprovalsDue } from '@/features/billing/ApprovalsDue';
import { Link, useSearchParams } from 'react-router-dom';
import { BookOpen, FileText, GraduationCap, Presentation, Upload, User } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Loading, PageHeader, Pagination, Panel, Stat } from '@/components/ui';
import { Stage, useDocPage } from '../shared';

interface DashboardData {
  template: 'user' | 'teacher';
  total_documents: number; draft_documents: number; review_documents: number; approved_documents: number;
  recent_documents: { id: number; document_number: string; document_name: string; stage_status: number; created_at: string }[];
  page: number; num_pages: number;
}

export default function DashboardPage() {
  const [params, setParams] = useSearchParams();
  const page = params.get('page') || undefined;
  const { can } = useAuth();
  const q = useDocPage<DashboardData>(['dashboard'], '/api/doccore/dashboard', { page });
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const teacher = d.template === 'teacher';

  const table = d.recent_documents.length > 0 ? (
    <div className="table-scroll">
      <table className="tbl">
        <thead><tr><th>Document Number</th><th>Document Name</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead>
        <tbody>
          {d.recent_documents.map((doc) => (
            <tr key={doc.id}>
              <td>{doc.document_number}</td>
              <td>{doc.document_name}</td>
              <td><Stage value={doc.stage_status} revisedLabel={teacher ? 'Needs Revision' : 'Revised'} /></td>
              <td>{formatDate(doc.created_at)}</td>
              <td><Link className="btn btn-primary btn-sm" to={`/content-lab-management/document/${doc.id}/`}>View</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* Django never passed the page object to the template, so only page 1 was reachable */}
      <Pagination page={d.page} pages={d.num_pages}
        onChange={(p) => setParams((prev) => { const n = new URLSearchParams(prev); n.set('page', String(p)); return n; })} />
    </div>
  ) : (
    <p className="muted">No documents found.{' '}
      {(teacher || can('can_upload')) && <Link className="act act-accent" to="/content-lab-management/upload/">Upload your first document</Link>}
    </p>
  );

  return (
    <div className="stack-lg">
      <PageHeader title={teacher ? 'Teacher Dashboard' : 'Dashboard'} />
      <ApprovalsDue />
      <div className="stat-grid">
        <Stat value={d.total_documents} label={teacher ? 'My Documents' : 'Total Documents'} />
        <Stat value={d.draft_documents} label="Draft Documents" />
        <Stat value={d.review_documents} label="Under Review" />
        <Stat value={d.approved_documents} label="Approved Documents" />
      </div>

      {teacher ? (
        <>
          <div className="detail-grid">
            <Panel title="My Recent Documents" flush>{table}</Panel>
            <Panel title="Teaching Resources">
              <div className="stack">
                <Link className="btn btn-secondary btn-block" to="/content-lab-management/reference-library/"><BookOpen size={14} /> Reference Library</Link>
                <a className="btn btn-secondary btn-block" href="#"><GraduationCap size={14} /> Course Materials</a>
                <a className="btn btn-secondary btn-block" href="#"><Presentation size={14} /> Teaching Guidelines</a>
              </div>
            </Panel>
          </div>
          <Panel title="Teacher Tools">
            <div className="dc-quick">
              <Link className="btn btn-primary" to="/content-lab-management/upload/"><Upload size={14} /> Upload Document</Link>
              <Link className="btn btn-secondary" to="/content-lab-management/library/"><BookOpen size={14} /> Document Library</Link>
              <Link className="btn btn-secondary" to="/content-lab-management/reference-library/"><FileText size={14} /> References</Link>
              <Link className="btn btn-secondary" to="/profile/"><User size={14} /> My Profile</Link>
            </div>
          </Panel>
        </>
      ) : (
        <>
          <Panel title="Recent Documents" flush>{table}</Panel>
          <Panel title="Quick Actions">
            <div className="dc-quick">
              {can('can_upload') && <Link className="btn btn-primary" to="/content-lab-management/upload/"><Upload size={14} /> Upload Document</Link>}
              {can('can_access_library') && <Link className="btn btn-secondary" to="/content-lab-management/library/"><BookOpen size={14} /> Document Library</Link>}
              {can('can_access_references') && <Link className="btn btn-secondary" to="/content-lab-management/reference-library/"><FileText size={14} /> References</Link>}
              <Link className="btn btn-secondary" to="/profile/"><User size={14} /> My Profile</Link>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
