/** Port of templates/library/reference_detail.html (library.views.reference_detail_view). */
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Download, ExternalLink, Eye, FileText, Trash2 } from 'lucide-react';
import { api, authUrl } from '@/lib/api';
import { useAuth, useUser } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { Badge, ErrorNotice, Loading, PageHeader, Panel, Spinner, useConfirm } from '@/components/ui';
import { useActionFeedback, useLibraryPage, type ReferenceDetail } from '../api';
import '../library.css';

export default function ReferenceDetailPage() {
  const { referenceId } = useParams();
  const user = useUser();
  const { can } = useAuth();
  const confirm = useConfirm();
  const feedback = useActionFeedback();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const q = useLibraryPage<{ reference: ReferenceDetail }>(['reference', referenceId], `/api/library/references/${referenceId}`);

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const r = q.data!.reference;
  const fileUrl = authUrl(`/api/library/references/${r.id}/file`);
  const downloadUrl = authUrl(`/api/library/references/${r.id}/file?download=1`);
  const canDelete = can('can_delete_library');

  const deleteReference = async () => {
    const ok = await confirm({
      title: 'Delete reference',
      message: 'Are you sure you want to delete this reference? This action cannot be undone.',
      confirmLabel: 'Delete', danger: true,
    });
    if (!ok) return;
    setDeleting(true);
    try {
      const { data } = await api.delete(`/api/library/references/${r.id}`);
      feedback.success(data, '/content-lab-management/reference-library/');
    } catch (err) {
      feedback.failure(err);
      if (!(err as any)?.response?.data?.redirect) navigate('/content-lab-management/reference-library/');
    } finally {
      setDeleting(false);
    }
  };

  const fileButtons = (small: boolean, previewLabel: string, openLabel: string) => r.has_file && (
    <>
      <Link to={`/content-lab-management/reference-preview/${r.id}/`} className={`btn btn-secondary ${small ? 'btn-sm' : ''}`}><Eye size={14} /> {previewLabel}</Link>
      <a href={downloadUrl} className={`btn btn-secondary ${small ? 'btn-sm' : ''}`}><Download size={14} /> {small ? 'Download File' : 'Download'}</a>
      <a href={fileUrl} target="_blank" rel="noreferrer" className={`btn btn-primary ${small ? 'btn-sm' : ''}`}><ExternalLink size={14} /> {openLabel}</a>
    </>
  );

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow={<><Link to="/content-lab-management/reference-library/">Reference Library</Link> / {r.reference_number}</>}
        title="Reference Detail"
      />

      <Panel
        title={<span className="row-tight"><FileText size={15} /> {r.reference_number}</span>}
        actions={fileButtons(true, 'Preview', 'Open File')}
        footer={
          <div className="stack">
            <div className="between wrap">
              <Link to="/content-lab-management/reference-library/" className="btn btn-secondary"><ArrowLeft size={14} /> Back to Reference Library</Link>
              <div className="row wrap">
                {fileButtons(false, 'Preview with Annotations', 'View File')}
                {canDelete ? (
                  <button type="button" className="btn btn-danger" onClick={deleteReference} disabled={deleting}>
                    {deleting ? <><Spinner /> Deleting...</> : <><Trash2 size={14} /> Delete</>}
                  </button>
                ) : (
                  <small className="muted">Delete not available: No delete permission</small>
                )}
              </div>
            </div>
          </div>
        }
      >
        <div className="grid-2" style={{ gridTemplateColumns: '2fr 1fr' }}>
          <div>
            <div className="section-title" style={{ marginTop: 0 }}>Basic Information</div>
            <dl className="kv">
              <dt>Reference Number:</dt><dd><Badge tone="accent">{r.reference_number}</Badge></dd>
              <dt>Document Name:</dt><dd>{r.document_name}</dd>
              <dt>Type:</dt><dd><Badge tone="accent">{r.type_display}</Badge></dd>
              <dt>Subtype:</dt><dd><Badge>{r.subtype_display}</Badge></dd>
              <dt>Country:</dt><dd>{r.country}</dd>
              <dt>Therapeutic Area:</dt>
              <dd>{r.therapeutic_area ? <Badge tone="accent">{r.therapeutic_area}</Badge> : <span className="muted">Not specified</span>}</dd>
            </dl>
          </div>
          <div>
            <div className="section-title" style={{ marginTop: 0 }}>Metadata</div>
            <dl className="kv" style={{ gridTemplateColumns: '1fr' }}>
              <dt>Reference Year:</dt><dd className="muted">{r.ref_year ?? 'Not specified'}</dd>
              <dt>Reference Number:</dt><dd className="muted">{r.ref_number || 'Not specified'}</dd>
              <dt>Created By:</dt><dd className="muted">{r.created_by}</dd>
              <dt>Created At:</dt><dd className="muted">{formatDateTime(r.created_at)}</dd>
              <dt>Last Modified:</dt><dd className="muted">{formatDateTime(r.updated_at)}</dd>
            </dl>
          </div>
        </div>

        {r.has_file && (
          <>
            <hr className="hairline" style={{ margin: '20px 0' }} />
            <div className="section-title" style={{ marginTop: 0 }}>File Information</div>
            <div className="grid-3">
              <div><div className="small muted">File Name:</div>{r.file_name}</div>
              <div><div className="small muted">File Extension:</div><Badge>{(r.file_extension || '').toUpperCase()}</Badge></div>
              <div><div className="small muted">File Title:</div>{r.file_title_name}</div>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
