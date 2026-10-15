/** create_new_version — documents/create_version.html */
import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Archive, FileText, Info, Upload, X } from 'lucide-react';
import { api, toFormData } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { BackLink, Badge, ErrorNotice, Field, Loading, PageHeader, Panel, Spinner } from '@/components/ui';
import { Stage, useDocPage, useSubmitHandlers } from '../shared';

interface Data {
  document: { id: number; document_name: string; document_number: string; document_type: string | null; brand: string | null; stage_status: number; owner_name: string };
  versions_count: number; first_version_number: string | null; new_version_number: string; created_by_name: string;
  versions: { id: number; version_number: string; file_title_name: string; stage_status: number; created_at: string }[];
}

export default function NewVersionPage() {
  const { documentId } = useParams();
  const q = useDocPage<Data>(['new-version', documentId], `/api/doccore/documents/${documentId}/new-version`);
  const { onSuccess, onError } = useSubmitHandlers();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const doc = d.document;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) { window.alert('Please select a file to upload'); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/api/doccore/documents/${doc.id}/new-version`, toFormData({ document_file: file }));
      onSuccess(data);
    } catch (err) {
      setBusy(false);
      onError(err);
    }
  };

  return (
    <div className="page-narrow stack-lg">
      <BackLink to={`/content-lab-management/document/${documentId}/`}>Back to document</BackLink>
      <PageHeader title="Create New Version" subtitle={doc.document_name} />
      <Panel title={<span className="row-tight"><FileText size={15} className="dc-accent" /> {doc.document_name}</span>}>
        <div className="grid-2">
          <dl className="kv">
            <dt>Document #:</dt><dd><strong>{doc.document_number}</strong></dd>
            <dt>Type:</dt><dd>{doc.document_type || '-'}</dd>
            <dt>Brand:</dt><dd>{doc.brand || '-'}</dd>
          </dl>
          <dl className="kv">
            <dt>Status:</dt><dd><Stage value={doc.stage_status} revisedLabel="Revised" /></dd>
            <dt>Versions:</dt><dd><Badge tone="accent">{d.versions_count}</Badge></dd>
            <dt>Owner:</dt><dd>{doc.owner_name}</dd>
          </dl>
        </div>
      </Panel>

      <Panel title={<span className="row-tight"><Upload size={15} /> Upload New Version</span>}>
        <form onSubmit={submit} className="stack">
          <Field label="Select Document File" required help="Supported formats: PDF, DOC, DOCX, TXT, RTF. Maximum file size: 50MB.">
            <input type="file" className="input" required accept=".pdf,.doc,.docx,.txt,.rtf"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                if (f && f.size > 50 * 1024 * 1024) { window.alert('File size must be less than 50MB'); e.target.value = ''; setFile(null); return; }
                setFile(f);
              }} />
          </Field>
          <div className="well">
            <div className="dc-section-title row-tight"><Info size={13} /> Version Information</div>
            <div className="grid-2 small muted">
              <div>
                <div><strong>Current Versions:</strong> {d.versions_count}</div>
                {d.first_version_number && <div><strong>Latest Version:</strong> {d.first_version_number}</div>}
              </div>
              <div>
                <div><strong>New Version Number:</strong> {d.new_version_number}</div>
                <div><strong>Created By:</strong> {d.created_by_name}</div>
              </div>
            </div>
          </div>
          <div className="between">
            <Link to={`/content-lab-management/document/${doc.id}/`} className="btn btn-secondary"><X size={14} /> Cancel</Link>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? <Spinner label="Uploading..." /> : <><Upload size={14} /> Upload New Version</>}
            </button>
          </div>
        </form>
      </Panel>

      {d.versions.length > 0 && (
        <Panel title={<span className="row-tight"><Archive size={15} /> Existing Versions</span>} flush>
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th>Version</th><th>File Name</th><th>Status</th><th>Created</th></tr></thead>
              <tbody>
                {d.versions.map((v, i) => (
                  <tr key={v.id}>
                    <td><strong>{v.version_number}</strong> {i === 0 && <Badge tone="ok">Latest</Badge>}</td>
                    <td>{v.file_title_name}</td>
                    <td><Stage value={v.stage_status} /></td>
                    <td>{formatDate(v.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}
