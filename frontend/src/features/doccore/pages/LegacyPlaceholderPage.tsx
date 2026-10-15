/**
 * Legacy Django views whose templates never existed in the original project
 * (upload_reference.html, document_for_review.html, upload_version.html, reference_history.html,
 * upload_reference_zip.html, complete.html, enable_editing.html). Django answered them with a
 * TemplateDoesNotExist error page; here they show an "unavailable" notice with the same page title.
 * complete/ and enable-editing/ keep their redirect to documents:home when no ?id= is given and
 * their 404 for an unknown version.
 */
import { Navigate, useSearchParams } from 'react-router-dom';
import { ErrorNotice, Loading, PageHeader } from '@/components/ui';
import { useDocPage } from '../shared';

function Unavailable({ title }: { title: string }) {
  return (
    <div className="stack-lg">
      <PageHeader title={title} />
      <div className="notice notice-warn">This page is not available.</div>
    </div>
  );
}

function VersionPage({ title, id }: { title: string; id: string }) {
  const q = useDocPage<{ id: number }>(['version-exists', id], `/api/doccore/versions/${id}/exists`);
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  return <Unavailable title={title} />;
}

export default function LegacyPlaceholderPage({ title, needsVersionId }: { title: string; needsVersionId?: boolean }) {
  const [params] = useSearchParams();
  if (needsVersionId) {
    const id = params.get('id');
    if (!id) return <Navigate to="/content-lab-management/dashboard/" replace />;
    return <VersionPage title={title} id={id} />;
  }
  return <Unavailable title={title} />;
}
