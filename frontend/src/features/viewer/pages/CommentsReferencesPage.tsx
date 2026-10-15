/** Comments & References — port of templates/documents/comments_references.html (/documents/comments/<id>/). */
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Calendar, ExternalLink, Eye, FileText, Globe, History, Link2, MessageSquare, Plus, UserCog } from 'lucide-react';
import { useUser } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { Badge, Empty, ErrorNotice, Loading, Panel } from '@/components/ui';
import { type ViewerDocument, type ViewerReference, type ViewerUser, type ViewerVersion, fileUrl, usePageData } from '../api';
import { truncateChars } from './PreviewPage';
import '../viewer.css';

interface Review {
  id: number; user: ViewerUser; is_completed: boolean; completed_at: string | null; started_at: string | null;
  remarks: string | null; created_at: string | null; modified_by: ViewerUser | null;
}
interface CommentsData { version: ViewerVersion; document: ViewerDocument; references: ViewerReference[]; reviews: Review[] }

function titleCase(v: string) { return (v || '').replace(/\w\S*/g, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()); }

/** Django `linebreaks` filter: paragraphs on blank lines, <br> on single newlines. */
function Linebreaks({ text }: { text: string }) {
  return <>{text.split(/\n{2,}/).map((p, i) => <p key={i}>{p.split('\n').map((l, j) => <span key={j}>{j > 0 && <br />}{l}</span>)}</p>)}</>;
}

export default function CommentsReferencesPage() {
  const { versionId } = useParams();
  const user = useUser();
  const q = usePageData<CommentsData>(['comments', versionId], `/api/viewer/versions/${versionId}/comments`);
  if (q.isLoading) return <Loading />;
  if (q.error) return (q.error.response?.data as any)?.redirect ? <Loading /> : <ErrorNotice error={q.error} />;
  if (!q.data) return null;
  const { version, document: doc, references, reviews } = q.data;
  const canManage = user.user_type === 'manager' || user.is_manager || doc.user.id === user.id;

  return (
    <div className="vw-page">
      <header className="page-header">
        <div className="grow">
          <div className="eyebrow">Comments &amp; References</div>
          <h1 className="row"><MessageSquare size={20} /> Comments &amp; References</h1>
          <p className="muted page-subtitle">{version.file_title_name} - Version {version.version_number}</p>
        </div>
        <Link to={`/content-lab-management/preview/${version.id}/`} className="btn btn-secondary btn-sm"><ArrowLeft size={14} /> Back to Preview</Link>
      </header>

      <Panel>
        <div className="grid-2">
          <dl className="kv"><dt>Document</dt><dd>{doc.document_name}</dd><dt>Document Number</dt><dd>{doc.document_number}</dd></dl>
          <dl className="kv"><dt>Owner</dt><dd>{doc.user.first_name} {doc.user.last_name}</dd><dt>Created</dt><dd>{formatDateTime(version.created_at)}</dd></dl>
        </div>
      </Panel>

      <div className="grid-2 vw-mt">
        <Panel title={<span className="row"><MessageSquare size={15} /> Reviews &amp; Comments ({reviews.length})</span>}>
          <div className="vw-scroll">
            {reviews.length === 0 ? (
              <Empty title="No reviews or comments yet">Reviews and comments from assigned reviewers will appear here.</Empty>
            ) : reviews.map((r) => (
              <div key={r.id} className={`vw-card ${r.is_completed ? 'is-ok' : 'is-warn'}`}>
                <div className="between">
                  <div>
                    <strong>{r.user.first_name} {r.user.last_name}</strong>
                    <div className="muted small">{titleCase(r.user.user_type)}</div>
                  </div>
                  <div className="right">
                    {r.is_completed ? (
                      <><Badge tone="ok">Completed</Badge><div className="muted small">{formatDateTime(r.completed_at)}</div></>
                    ) : (
                      <><Badge tone="warn">In Progress</Badge><div className="muted small">Started: {r.started_at ? formatDateTime(r.started_at) : 'Not started'}</div></>
                    )}
                  </div>
                </div>
                {r.remarks && (
                  <div className="vw-mt">
                    <strong>Comments:</strong>
                    <div className="well small vw-remarks"><Linebreaks text={r.remarks} /></div>
                  </div>
                )}
                <div className="muted small vw-mt">
                  <Calendar size={12} /> Assigned: {formatDateTime(r.created_at)}
                  {r.modified_by && <><br /><UserCog size={12} /> Modified by: {r.modified_by.first_name} {r.modified_by.last_name}</>}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title={<span className="row"><Link2 size={15} /> Linked References ({references.length})</span>}
          actions={canManage ? <Link to={`/content-lab-management/version/${version.id}/link-references/`} className="btn btn-secondary btn-sm"><Plus size={14} /> Manage Links</Link> : undefined}>
          <div className="vw-scroll">
            {references.length === 0 ? (
              <Empty title="No references linked"
                action={canManage ? <Link to={`/content-lab-management/version/${version.id}/link-references/`} className="btn btn-primary"><Plus size={14} /> Link References</Link> : undefined}>
                Link relevant references to organize and connect related documents.
              </Empty>
            ) : references.map((r) => (
              <div key={r.id} className="vw-card between">
                <div className="grow">
                  <strong>{r.reference_number}</strong>
                  <p>{truncateChars(r.document_name, 100)}</p>
                  <div className="row wrap">
                    <Badge tone="accent">{r.type_display}</Badge>
                    <Badge>{r.subtype_display}</Badge>
                    {r.therapeutic_area && <Badge>{r.therapeutic_area}</Badge>}
                  </div>
                  <div className="muted small vw-mt"><Globe size={12} /> {r.country}{r.ref_year ? <> | <Calendar size={12} /> {r.ref_year}</> : null}</div>
                </div>
                <div className="stack">
                  <Link to={`/content-lab-management/reference-library/${r.id}/`} className="btn btn-secondary btn-sm btn-icon" title="View Details"><Eye size={14} /></Link>
                  {r.has_file && (
                    <a href={fileUrl(r.file_api)} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm btn-icon" title="Open File"><ExternalLink size={14} /></a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="between vw-mt">
        <Link to={`/content-lab-management/preview/${version.id}/`} className="btn btn-secondary"><ArrowLeft size={14} /> Back to Preview</Link>
        <div className="row">
          <Link to={`/content-lab-management/document/${doc.id}/`} className="btn btn-secondary"><FileText size={14} /> Document Details</Link>
          <Link to={`/content-lab-management/document/${doc.id}/history/`} className="btn btn-secondary"><History size={14} /> Version History</Link>
        </div>
      </div>
    </div>
  );
}
