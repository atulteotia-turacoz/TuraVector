/** Port of templates/library/manage_reviewers.html (library.views.manage_reviewers_view + toggle_reviewer_status). */
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Bell, CheckCircle2, Clock, Eye } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { BackLink, Badge, ErrorNotice, Loading, PageHeader, Panel, Stat, StageStatus, useToast } from '@/components/ui';
import { timePart, useLibraryPage } from '../api';
import '../library.css';

interface Assignment {
  id: number;
  reviewer_name: string;
  reviewer_email: string;
  reviewer_initials: string;
  version_id: number;
  version_number: string;
  review_date: string | null;
  is_completed: boolean;
  is_active: boolean;
  assigned_by: string;
  created_at: string;
}
interface Resp {
  document: { id: number; document_name: string; document_number: string; owner: string };
  has_approved_version: boolean;
  assignments: Assignment[];
}

export default function ManageReviewersPage() {
  const { documentId } = useParams();
  const toast = useToast();
  const q = useLibraryPage<Resp>(['manage-reviewers', documentId], `/api/library/documents/${documentId}/manage-reviewers`);
  const [active, setActive] = useState<Record<number, boolean>>({});
  useEffect(() => {
    if (q.data) setActive(Object.fromEntries(q.data.assignments.map((a) => [a.id, a.is_active])));
  }, [q.data]);

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const { document: doc, assignments } = q.data!;

  const toggle = async (id: number, checked: boolean) => {
    setActive((s) => ({ ...s, [id]: checked }));
    try {
      const { data } = await api.post(`/api/library/assignments/${id}/toggle-status`, {});
      if (data.success) {
        toast.success(data.message);
        setActive((s) => ({ ...s, [id]: !!data.is_active }));
      } else {
        toast.error(data.error || 'Error updating reviewer status');
        setActive((s) => ({ ...s, [id]: !checked }));
      }
    } catch (err: any) {
      toast.error(err?.response ? (err.response.data?.error || errorMessage(err, 'Error updating reviewer status')) : 'Network error occurred');
      setActive((s) => ({ ...s, [id]: !checked }));
    }
  };

  return (
    <div className="stack-lg">
      <BackLink to={`/content-lab-management/document/${documentId}/`}>Back to document</BackLink>
      <PageHeader
        eyebrow="Manage Reviewers"
        title={<>Document: {doc.document_name}</>}
        subtitle={<>Number: {doc.document_number} | Owner: {doc.owner}</>}
        actions={<Link to="/content-lab-management/library/" className="btn btn-secondary"><ArrowLeft size={14} /> Back to Library</Link>}
      />

      <Panel flush>
        <div className="table-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Reviewer</th><th>Version</th><th>Review Due</th><th>Status</th><th>Active</th>
                <th>Assigned By</th><th>Assigned Date</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assignments.length === 0 && (
                <tr><td colSpan={8}><div className="empty small">No reviewers assigned to this document yet.</div></td></tr>
              )}
              {assignments.map((a) => {
                const isOn = active[a.id] ?? a.is_active;
                return (
                  <tr key={a.id} className={isOn ? '' : 'lib-row-inactive'}>
                    <td>
                      <div className="row">
                        <span className="lib-avatar">{a.reviewer_initials}</span>
                        <div><strong>{a.reviewer_name}</strong><span className="lib-cell-sub">{a.reviewer_email}</span></div>
                      </div>
                    </td>
                    <td><Badge>v{a.version_number}</Badge></td>
                    <td>{a.review_date ? formatDate(a.review_date) : <span className="faint">Not set</span>}</td>
                    <td>
                      {a.is_completed
                        ? <span className="row-tight"><CheckCircle2 size={13} /><StageStatus label="Completed" tone="accent" /></span>
                        : <span className="row-tight"><Clock size={13} /><StageStatus label="Pending" tone="ok" /></span>}
                    </td>
                    <td>
                      <label className="lib-switch" title={isOn ? 'Active' : 'Inactive'}>
                        <input type="checkbox" checked={isOn} disabled={a.is_completed} onChange={(e) => toggle(a.id, e.target.checked)} />
                        <span />
                      </label>
                    </td>
                    <td>{a.assigned_by}</td>
                    <td className="nowrap">{formatDate(a.created_at)}<span className="lib-cell-sub">{timePart(formatDateTime(a.created_at))}</span></td>
                    <td>
                      <span className="lib-icon-btns">
                        <Link to={`/content-lab-management/preview/${a.version_id}/`} className="btn btn-secondary btn-icon" title="View Document"><Eye size={14} /></Link>
                        {!a.is_completed && (
                          <button type="button" className="btn btn-secondary btn-icon" title="Send Reminder"
                            onClick={() => toast.info('Reminder functionality coming soon')}><Bell size={14} /></button>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {assignments.length > 0 && (
        // Values mirror the Django template exactly (it rendered the total twice and hard-coded 0s).
        <div className="stat-grid">
          <Stat value={assignments.length} label="Total Assignments" />
          <Stat value={assignments.length} label="Active Assignments" />
          <Stat value={0} label="Completed Reviews" />
          <Stat value={0} label="Overdue Reviews" />
        </div>
      )}
    </div>
  );
}
