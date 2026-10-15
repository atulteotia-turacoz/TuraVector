/** Port of templates/library/reference_zip_detail.html (library.views.reference_zip_detail_view). */
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Download, FileText, Trash2 } from 'lucide-react';
import { api, authUrl } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { Badge, ErrorNotice, Loading, PageHeader, Panel, useConfirm } from '@/components/ui';
import { filesizeformat, useActionFeedback, useLibraryPage, type ZipDetail } from '../api';
import '../library.css';

export default function ReferenceZipDetailPage() {
  const { zipId } = useParams();
  const { can } = useAuth();
  const confirm = useConfirm();
  const feedback = useActionFeedback();
  const q = useLibraryPage<{ ref_zip: ZipDetail }>(['zip', zipId], `/api/library/reference-zips/${zipId}`);

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const z = q.data!.ref_zip;
  const zipUrl = authUrl(`/api/library/reference-zips/${z.id}/file`);
  const canDelete = can('can_delete_library');

  const confirmDelete = async () => {
    const ok = await confirm({
      title: 'Delete reference ZIP',
      message: 'Are you sure you want to delete this reference ZIP file? This action cannot be undone.',
      confirmLabel: 'Delete', danger: true,
    });
    if (!ok) return;
    try {
      const { data } = await api.delete(`/api/library/reference-zips/${z.id}`);
      feedback.success(data, '/content-lab-management/references/');
    } catch (err) {
      feedback.failure(err);
    }
  };

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow={<><Link to="/content-lab-management/dashboard/">Home</Link> / <Link to="/content-lab-management/references/">Document References</Link> / {z.reference_zip_number}</>}
        title={z.reference_zip_number}
        subtitle="Reference ZIP Details"
        actions={<>
          {z.has_file && <a href={zipUrl} className="btn btn-primary"><Download size={14} /> Download ZIP</a>}
          <Link to="/content-lab-management/references/" className="btn btn-secondary"><ArrowLeft size={14} /> Back to List</Link>
        </>}
      />

      <div className="grid-2">
        <Panel title="File Information">
          <dl className="kv">
            <dt>Reference Number:</dt><dd>{z.reference_zip_number}</dd>
            <dt>File Name:</dt><dd>{z.file_title_name}</dd>
            <dt>File Extension:</dt><dd><Badge tone="accent">.{(z.file_extension || '').toUpperCase()}</Badge></dd>
            <dt>File Size:</dt><dd>{z.has_file && z.file_size !== null ? filesizeformat(z.file_size) : '-'}</dd>
            <dt>Created Date:</dt><dd>{formatDateTime(z.created_at)}</dd>
            <dt>Last Modified:</dt><dd>{formatDateTime(z.updated_at)}</dd>
          </dl>
        </Panel>
        <Panel title="Associated Document">
          <dl className="kv">
            <dt>Document Name:</dt><dd>{z.document.document_name}</dd>
            <dt>Document Number:</dt><dd>{z.document.document_number}</dd>
            <dt>Version:</dt><dd><Badge tone="accent">{z.version.version_number}</Badge></dd>
            <dt>Document Type:</dt><dd>{z.document.document_type ?? ''}</dd>
            <dt>Document Status:</dt><dd><Badge>{z.document.stage_status_display}</Badge></dd>
          </dl>
        </Panel>
        <Panel title="User Information">
          <dl className="kv">
            <dt>Uploaded By:</dt><dd>{z.created_by}</dd>
            <dt>Modified By:</dt><dd>{z.modified_by}</dd>
            <dt>Owner:</dt><dd>{z.owner}</dd>
          </dl>
        </Panel>
        <Panel title="Description">
          <p>This ZIP file contains reference documents related to the associated document version.
            Reference ZIP files are used to bundle multiple supporting documents together for easy management and distribution.</p>
        </Panel>
      </div>

      <Panel title="Actions">
        <div className="row wrap">
          {z.has_file && <a href={zipUrl} className="btn btn-primary"><Download size={14} /> Download ZIP File</a>}
          <Link to={`/content-lab-management/document/${z.document.id}/`} className="btn btn-secondary"><FileText size={14} /> View Document</Link>
          {canDelete && <button type="button" className="btn btn-danger" onClick={confirmDelete}><Trash2 size={14} /> Delete ZIP File</button>}
        </div>
      </Panel>
    </div>
  );
}
