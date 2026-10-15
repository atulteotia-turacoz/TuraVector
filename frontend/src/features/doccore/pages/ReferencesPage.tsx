/** references_view — documents/references.html (the user's reference ZIP files). */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Archive, BookOpen, Download, Eye, RotateCcw, Search, Trash2 } from 'lucide-react';
import { api, downloadFile, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { DataTable, ErrorNotice, Loading, PageHeader, useConfirm, useToast, type Column } from '@/components/ui';
import { RowMenu, filesizeformat, useDocPage } from '../shared';
import '@/features/library/library.css';

interface ZipRow {
  id: number; reference_zip_number: string; file_title_name: string; document_name: string; document_number: string;
  version_number: string; file_size: number | null; has_file: boolean; created_at: string;
}
interface Data { search_query: string; reference_zips: ZipRow[] }

export default function ReferencesPage() {
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const [term, setTerm] = useState(search);
  useEffect(() => setTerm(search), [search]);
  const { can } = useAuth();
  const confirm = useConfirm();
  const toast = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const q = useDocPage<Data>(['references'], '/api/doccore/references', { search });
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  const remove = async (id: number) => {
    const ok = await confirm({ title: 'Delete reference ZIP', danger: true, confirmLabel: 'Delete',
      message: 'Are you sure you want to delete this reference ZIP file? This action cannot be undone.' });
    if (!ok) return;
    try {
      const { data } = await api.delete(`/api/library/reference-zips/${id}`);
      toast.success(data.message);
    } catch (err: any) {
      toast.error(errorMessage(err));
      const redirect = err?.response?.data?.redirect;
      if (redirect && redirect !== '/content-lab-management/references/') navigate(redirect);
    }
    void qc.invalidateQueries({ queryKey: ['doccore', 'references'] });
  };

  const submit = (e: FormEvent) => { e.preventDefault(); setParams({ search: term }); };

  const download = (z: ZipRow) =>
    downloadFile(`/api/library/reference-zips/${z.id}/file`, undefined, `${z.file_title_name}`).catch((e) => toast.error(errorMessage(e)));

  const columns: Column<ZipRow>[] = [
    {
      key: 'file_title_name', header: 'ZIP file', value: (z) => `${z.file_title_name} ${z.reference_zip_number}`, render: (z) => (
        <div className="vr-file">
          <span className="vr-ext">ZIP</span>
          <span style={{ minWidth: 0 }}>
            <span className="vr-title" title={z.file_title_name}>{z.file_title_name}</span>
            <span className="vr-sub mono">{z.reference_zip_number}</span>
          </span>
        </div>
      ),
    },
    {
      key: 'document_name', header: 'Document', value: (z) => `${z.document_name} ${z.document_number}`, render: (z) => (
        <div className="md-doc">
          <span className="md-doc-name" title={z.document_name}>{z.document_name}</span>
          <span className="md-doc-number mono">{z.document_number} · {z.version_number.replace(`${z.document_number}-`, '')}</span>
        </div>
      ),
    },
    { key: 'file_size', header: 'Size', render: (z) => <span className="small tnum nowrap">{z.file_size ? filesizeformat(z.file_size) : '—'}</span> },
    {
      key: 'created_at', header: 'Created', render: (z) => {
        const [date, time] = [formatDateTime(z.created_at).replace(/ \d{1,2}:\d{2} [AP]M$/, ''), formatDateTime(z.created_at).match(/\d{1,2}:\d{2} [AP]M$/)?.[0]];
        return <span className="nowrap"><span className="small">{date}</span>{time && <span className="md-sub">{time}</span>}</span>;
      },
    },
    {
      key: 'actions', header: '', sortable: false, value: () => '', render: (z) => (
        <span className="lib-actions" onClick={(e) => e.stopPropagation()}>
          <Link className="btn btn-secondary btn-sm" title="View Details" to={`/content-lab-management/reference-zip/${z.id}/`}><Eye size={13} /><span className="lib-label">View</span></Link>
          {z.has_file && (
            <button type="button" className="btn btn-secondary btn-sm" title="Download ZIP" onClick={() => void download(z)}><Download size={13} /><span className="lib-label">Download</span></button>
          )}
          <RowMenu label={`More actions for ${z.reference_zip_number}`}>
            {(close) => (
              <button className="pop-item vr-danger" onClick={() => { close(); void remove(z.id); }}><Trash2 size={14} /> Delete ZIP file</button>
            )}
          </RowMenu>
        </span>
      ),
    },
  ];

  return (
    <div className="stack-lg">
      <PageHeader title="Document References" subtitle="ZIP files of reference documents attached to your document versions."
        actions={can('can_access_library') ? (<>
          <Link className="btn btn-secondary" to="/content-lab-management/reference-library/"><BookOpen size={14} /> View References</Link>
          {can('can_create_library') && <Link className="btn btn-primary" to="/content-lab-management/reference-library/upload-zip/"><Archive size={14} /> Upload ZIP</Link>}
        </>) : undefined} />

      <section className="panel">
        <div className="md-toolbar">
          <h2 className="row-tight">My ZIP files <span className="vr-count tnum">{d.reference_zips.length}</span></h2>
          <div className="row">
            <form className="search-input lib-search" onSubmit={submit}>
              <Search size={14} />
              <input className="input" placeholder="ZIP number, file or document name…" value={term} onChange={(e) => setTerm(e.target.value)} aria-label="Search" />
            </form>
            {search && <Link to="/content-lab-management/references/" className="btn btn-ghost btn-sm"><RotateCcw size={13} /> Clear</Link>}
          </div>
        </div>
        {d.reference_zips.length > 0
          ? <DataTable rows={d.reference_zips} columns={columns} rowKey={(z) => z.id} pageSize={25} searchable={false}
              onRowClick={(z) => navigate(`/content-lab-management/reference-zip/${z.id}/`)} />
          : (
            <div className="empty">
              <Archive size={32} className="faint" />
              <h3>No document reference ZIP files found</h3>
              <p>Upload ZIP files containing reference documents for your document versions.</p>
              <div className="row" style={{ justifyContent: 'center', marginTop: 12 }}>
                <Link className="btn btn-primary" to="/content-lab-management/reference-library/upload-zip/"><Archive size={14} /> Upload ZIP</Link>
                <Link className="btn btn-secondary" to="/content-lab-management/reference-library/"><BookOpen size={14} /> Browse References</Link>
              </div>
            </div>
          )}
      </section>
    </div>
  );
}
