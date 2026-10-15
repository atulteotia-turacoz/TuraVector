import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { API, formErrors } from '@/lib/admin';
import { ErrorNotice, Loading, PageHeader, Panel, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';
import { toastMessages } from './ChangeList';

interface Info {
  pk: string; str: string; title: string; annotation_count: number; allowed_extensions: string[]; help_text: string;
  version: { version_number: string; file_name: string; file_extension: string; file_title_name: string; stage_status: string;
    updated_at_display: string; url: string | null };
}

/** documents/admin_views.change_document_version_file + change_file.html */
export default function ChangeFile() {
  const { pk = '' } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'change-file', pk], queryFn: async () => (await api.get<Info>(`${API}/documentversion/${pk}/change-file`)).data, gcTime: 0 });
  const [file, setFile] = useState<File | null>(null);
  const [agree, setAgree] = useState(false);
  const [errors, setErrors] = useState<Record<string, string[]> | null>(null);
  const [busy, setBusy] = useState(false);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const v = d.version;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await confirm({
      title: 'Replace file?', danger: true, confirmLabel: 'Replace File',
      message: 'Are you sure you want to replace this file? This will permanently delete all annotations and cannot be undone.',
    });
    if (!ok) return;
    setBusy(true); setErrors(null);
    const fd = new FormData();
    if (file) fd.append('new_file', file);
    if (agree) fd.append('confirm_delete_annotations', 'on');
    try {
      const { data } = await api.post(`${API}/documentversion/${pk}/change-file`, fd);
      toastMessages(toast, data.messages);
      void qc.invalidateQueries({ queryKey: ['admin'] });
      navigate('/documents/documentversion/');
    } catch (err) {
      const fe = formErrors(err);
      if (fe?.errors) setErrors(fe.errors); else toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const errList = (k: string) => errors?.[k]?.length ? <ul className="errorlist" role="alert">{errors[k].map((x, i) => <li key={i}>{x}</li>)}</ul> : null;

  return (
    <>
      <Crumbs items={[
        { label: 'Documents', to: '/documents/' },
        { label: 'Document versions', to: '/documents/documentversion/' },
        { label: d.str, to: `/documents/documentversion/${pk}/change/` },
        { label: 'Change File' },
      ]} />
      <PageHeader title={d.title} />
      <div className="stack-lg">
        <Panel title="Current File Information">
          <dl className="kv">
            <dt>Version Number</dt><dd>{v.version_number}</dd>
            <dt>Current File</dt><dd>{v.url ? <a className="act" href={v.url} target="_blank" rel="noreferrer">{v.file_name}</a> : v.file_name}</dd>
            <dt>File Extension</dt><dd>{v.file_extension}</dd>
            <dt>File Title</dt><dd>{v.file_title_name}</dd>
            <dt>Status</dt><dd>{v.stage_status}</dd>
            <dt>Last Modified</dt><dd>{v.updated_at_display}</dd>
          </dl>
        </Panel>
        <div className="notice notice-warn">
          <div className="notice-title row-tight"><AlertTriangle size={14} /> Warning: This action will:</div>
          <ul style={{ paddingLeft: 18 }}>
            <li>Replace the current document file with the new one</li>
            <li>Delete the old file from the server</li>
            <li><strong>Permanently delete all {d.annotation_count} annotation(s)</strong> associated with this version</li>
            <li>This action cannot be undone</li>
          </ul>
        </div>
        <form onSubmit={submit} noValidate>
          <Panel title="Upload New File" flush>
            <div className={`form-row ${errors?.new_file ? 'has-error' : ''}`}>
              <label className="form-label required" htmlFor="new_file">New Document File</label>
              <div>
                {errList('new_file')}
                <input id="new_file" type="file" accept={d.allowed_extensions.map((x) => `.${x}`).join(',')} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                <span className="field-help">{d.help_text}</span>
              </div>
            </div>
            <div className={`form-row ${errors?.confirm_delete_annotations ? 'has-error' : ''}`}>
              <label className="form-label required" htmlFor="confirm_delete">Confirm deletion of all annotations</label>
              <div>
                {errList('confirm_delete_annotations')}
                <input id="confirm_delete" type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} style={{ marginTop: 9, accentColor: 'var(--accent)' }} />
                <span className="field-help">Check this box to confirm that all annotations for this version will be permanently deleted.</span>
              </div>
            </div>
          </Panel>
          <div className="submit-row">
            <button className="btn btn-danger" disabled={busy}>Replace File</button>
            <Link className="btn btn-secondary" to="/documents/documentversion/">Cancel</Link>
          </div>
        </form>
      </div>
    </>
  );
}
