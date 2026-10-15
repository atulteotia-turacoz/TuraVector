/**
 * Small viewer routes:
 *  - DraftPage            /documents/draft/ and /documents/draft/<id>/  (documents.views.draft_view)
 *  - EditorRedirectPage   /documents/editor/<id>/                       (documents.views.document_editor)
 *  - DownloadAnnotatedPage /documents/download/<id>/annotated/          (documents.views.download_annotated_document)
 */
import { useEffect, useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, authUrl, errorMessage } from '@/lib/api';
import { ErrorNotice, Loading, PageHeader, useToast } from '@/components/ui';
import { type ViewerDocument, type ViewerVersion, usePageData } from '../api';

/**
 * Django's draft_view checked permissions and then rendered 'documents/draft.html', a template that
 * does not exist in the project (the page always failed). The permission check is kept; the page
 * explains that no draft view exists. `/content-lab-management/draft/` without an id failed in Django as well.
 */
export function DraftPage() {
  const { versionId } = useParams();
  const q = usePageData<{ version: ViewerVersion; document: ViewerDocument }>(['draft', versionId],
    versionId ? `/api/viewer/versions/${versionId}/draft` : null);
  if (!versionId) return <ErrorNotice title="Draft" error={new Error('No document version specified.')} />;
  if (q.isLoading) return <Loading />;
  if (q.error) return (q.error.response?.data as any)?.redirect ? <Loading /> : <ErrorNotice error={q.error} />;
  if (!q.data) return null;
  return (
    <div>
      <PageHeader eyebrow="Draft" title={q.data.version.file_title_name} subtitle={q.data.version.version_number} />
      <div className="notice notice-warn">
        <div>
          <div className="notice-title">Draft view not available</div>
          The original application had no draft page template for this view. Use the document preview instead.
          <div className="row vw-mt">
            <Link className="btn btn-primary btn-sm" to={`/content-lab-management/preview/${q.data.version.id}/`}>Open Preview</Link>
            <Link className="btn btn-secondary btn-sm" to={`/content-lab-management/document/${q.data.document.id}/`}>Document Details</Link>
          </div>
        </div>
      </div>
    </div>
  );
}

/** /documents/editor/<id>/ → the same checks as Django, then the OnlyOffice editor (or back with a message). */
export function EditorRedirectPage() {
  const { versionId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    api.get(`/api/viewer/editor/${versionId}`).then(({ data }) => {
      if (data.message) {
        if (data.level === 'warning') toast.warning(data.message); else toast.error(data.message);
      }
      navigate(data.redirect, { replace: true });
    }).catch((err) => {
      toast.error(errorMessage(err));
      navigate('/content-lab-management/dashboard/', { replace: true });
    });
  }, [versionId, navigate, toast]);
  return <Loading label="Opening editor…" />;
}

/** /documents/download/<id>/annotated/ → the annotated PDF (or the original file), via the API. */
export function DownloadAnnotatedPage() {
  const { versionId } = useParams();
  useEffect(() => {
    window.location.replace(authUrl(`/api/viewer/versions/${versionId}/download-annotated`));
  }, [versionId]);
  return <Loading label="Preparing download…" />;
}
