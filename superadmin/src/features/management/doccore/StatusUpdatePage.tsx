/** update_document_status / update_version_status — documents/update_status.html, update_version_status.html */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/lib/api';
import { ErrorNotice, Field, Loading, PageHeader, Panel, useConfirm } from '@/components/ui';
import { useDocPage, useSubmitHandlers } from './shared';

interface Choice { value: number; label: string }
interface DocData {
  page_title: string; choices: Choice[];
  document: { id: number; document_number: string; document_name: string; stage_status: number; stage_status_display: string };
}
interface VersionData {
  page_title: string; choices: Choice[];
  version: { id: number; version_number: string; stage_status: number; stage_status_display: string };
  document: { id: number; document_number: string; document_name: string };
}

export default function StatusUpdatePage({ kind }: { kind: 'document' | 'version' }) {
  const { documentId, versionId } = useParams();
  const url = kind === 'document' ? `/api/doccore/documents/${documentId}/status` : `/api/doccore/versions/${versionId}/status`;
  const q = useDocPage<DocData | VersionData>(['status', kind, documentId ?? versionId], url);
  const { onSuccess, onError } = useSubmitHandlers();
  const confirm = useConfirm();
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | undefined>();
  useEffect(() => {
    if (!q.data) return;
    setValue(String('version' in q.data ? q.data.version.stage_status : q.data.document.stage_status));
  }, [q.data]);
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const isVersion = 'version' in d;
  const current = isVersion ? (d as VersionData).version.stage_status_display : (d as DocData).document.stage_status_display;
  const documentIdValue = d.document.id;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const newLabel = d.choices.find((c) => String(c.value) === value)?.label ?? '';
    const ok = await confirm({ title: d.page_title, message: `Are you sure you want to change the status from "${current}" to "${newLabel}"?` });
    if (!ok) return;
    setError(undefined);
    try {
      const { data } = await api.post(url, { stage_status: value });
      onSuccess(data);
    } catch (err) {
      onError(err, (errs) => setError(errs.stage_status));
    }
  };

  return (
    <div className="page-narrow stack-lg">
      <PageHeader title={d.page_title} />
      <Panel title={isVersion ? 'Update Version Status' : 'Update Document Status'}>
        <div className="notice notice-accent" style={{ marginBottom: 16 }}>
          <div>
            <strong>Document:</strong> {d.document.document_number} - {d.document.document_name}<br />
            {isVersion && <><strong>Version:</strong> {(d as VersionData).version.version_number}<br /></>}
            <strong>Current Status:</strong> {current}
          </div>
        </div>
        <form onSubmit={submit} className="stack">
          <Field label={isVersion ? 'Version Status' : 'Document Status'} error={error}>
            <select className="input" value={value} onChange={(e) => setValue(e.target.value)}>
              {d.choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </Field>
          {isVersion && (
            <div className="notice notice-warn">
              <span><strong>Note:</strong> Changing version status to "Under Review" or "Approved" will also update the parent document's status.</span>
            </div>
          )}
          <div className="row">
            <button type="submit" className="btn btn-primary">Update Status</button>
            <Link to={`/documents/document/${documentIdValue}/`} className="btn btn-secondary">Cancel</Link>
          </div>
        </form>
      </Panel>
    </div>
  );
}
