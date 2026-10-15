/** Port of templates/library/reference_library.html (library.views.reference_library_view). */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Download, ExternalLink, Eye, FileText, Lock, Plus, Search, Trash2 } from 'lucide-react';
import { api, authUrl, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { DataTable, Empty, ErrorNotice, Loading, Modal, PageHeader, Spinner, useConfirm, useToast, type Column } from '@/components/ui';
import { RowMenu } from '@/features/doccore/shared';
import { useActionFeedback, useLibraryPage, type ReferenceRow } from '../api';
import '../library.css';

interface Resp { references: ReferenceRow[]; reference_types: [string, string][]; selected: { search: string; type: string; brand: string } }

export default function ReferenceLibraryPage() {
  const { can } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const feedback = useActionFeedback();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const applied = { search: params.get('search') || '', type: params.get('type') || '', brand: params.get('brand') || '' };
  const [search, setSearch] = useState(applied.search);
  const [type, setType] = useState(applied.type);
  useEffect(() => { setSearch(applied.search); setType(applied.type); }, [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [opening, setOpening] = useState<number | null>(null);
  const [lockedOpen, setLockedOpen] = useState(false);

  const q = useLibraryPage<Resp>(['references'], '/api/library/references', applied);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (search) next.set('search', search);
    if (applied.type) next.set('type', applied.type);
    setParams(next);
  };

  const openInOffice365 = async (id: number) => {
    setOpening(id);
    try {
      const { data } = await api.post(`/api/office365/reference/open/${id}`, {});
      if (data?.error) {
        if (data.is_locked) setLockedOpen(true);
        else window.alert(`Error: ${data.error}`);
      } else {
        window.open(data.edit_url, '_blank');
      }
    } catch (err: any) {
      const body = err?.response?.data;
      if (body?.is_locked) setLockedOpen(true);
      else if (body?.error) window.alert(`Error: ${body.error}`);
      else window.alert(`Failed to open in Office 365: ${errorMessage(err)}`);
    } finally {
      setOpening(null);
    }
  };

  const deleteReference = async (id: number) => {
    const ok = await confirm({
      title: 'Delete reference',
      message: 'Are you sure you want to delete this reference? This action cannot be undone.',
      confirmLabel: 'Delete', danger: true,
    });
    if (!ok) return;
    try {
      const { data } = await api.delete(`/api/library/references/${id}`);
      toast.success(data.message);
    } catch (err) {
      feedback.failure(err);
    }
    void qc.invalidateQueries({ queryKey: ['library', 'references'] });
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const refs = q.data!.references;
  const fileUrl = (id: number) => authUrl(`/api/library/references/${id}/file`);

  const TYPE_TABS: [string, string][] = [['', 'All'], ['primary', 'Primary'], ['secondary', 'Secondary'], ['supporting', 'Supporting']];
  const setTypeNow = (t: string) => {
    const next = new URLSearchParams();
    if (applied.search) next.set('search', applied.search);
    if (t) next.set('type', t);
    setParams(next);
  };

  const columns: Column<ReferenceRow>[] = [
    {
      key: 'document_name', header: 'Reference', value: (r) => `${r.document_name} ${r.reference_number}`, render: (r) => (
        <div className="md-doc">
          <span className="md-doc-name" title={r.document_name}>{r.document_name}</span>
          <span className="md-doc-number mono">{r.reference_number}</span>
        </div>
      ),
    },
    {
      key: 'type_display', header: 'Type', render: (r) => (
        <span className="nowrap"><span className="small">{r.type_display}</span><span className="md-sub">{r.subtype_display}</span></span>
      ),
    },
    { key: 'therapeutic_area', header: 'Therapeutic area', render: (r) => r.therapeutic_area || <span className="faint">—</span> },
    { key: 'ref_year', header: 'Year', render: (r) => <span className="tnum">{r.ref_year ?? <span className="faint">—</span>}</span> },
    {
      key: 'actions', header: '', sortable: false, render: (r) => (
        <span className="lib-actions" onClick={(e) => e.stopPropagation()}>
          <Link to={`/content-lab-management/reference-library/${r.id}/`} className="btn btn-secondary btn-sm" title="View"><Eye size={13} /><span className="lib-label">View</span></Link>
          {r.has_file && (
            <a href={fileUrl(r.id)} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm" title="Download"><Download size={13} /><span className="lib-label">Download</span></a>
          )}
          <RowMenu label={`More actions for ${r.reference_number}`}>
            {(close) => (
              <>
                {r.has_file && (
                  <>
                    <a className="pop-item" href={fileUrl(r.id)} target="_blank" rel="noreferrer" onClick={close}><ExternalLink size={14} /> Open file in new tab</a>
                    <button className="pop-item" disabled={opening === r.id} onClick={() => { close(); void openInOffice365(r.id); }}>
                      {opening === r.id ? <Spinner /> : <FileText size={14} />} Open in Office 365
                    </button>
                    <div className="pop-sep" />
                  </>
                )}
                <button className="pop-item vr-danger" onClick={() => { close(); void deleteReference(r.id); }}><Trash2 size={14} /> Delete reference</button>
              </>
            )}
          </RowMenu>
        </span>
      ),
    },
  ];

  return (
    <div className="stack-lg">
      <PageHeader title="Reference Library" subtitle="Reference documents you can link to document versions."
        actions={can('can_create_library') ? <Link to="/content-lab-management/reference-library/upload/" className="btn btn-primary"><Plus size={14} /> Add New Reference</Link> : undefined} />

      <section className="panel">
        <div className="md-toolbar">
          <div className="filter-tabs" role="tablist" aria-label="Reference type">
            {TYPE_TABS.map(([v, label]) => (
              <button key={label} role="tab" aria-selected={applied.type === v} className={`filter-tab ${applied.type === v ? 'active' : ''}`}
                onClick={() => setTypeNow(v)}>{label}</button>
            ))}
          </div>
          <div className="row">
            <span className="small muted">{refs.length} reference{refs.length === 1 ? '' : 's'}</span>
            <form className="search-input lib-search" onSubmit={submit}>
              <Search size={14} />
              <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Document name or reference number" aria-label="Search" />
            </form>
          </div>
        </div>
        {refs.length === 0 ? (
          can('can_create_library') ? (
            <Empty title="No references found" action={<Link to="/content-lab-management/reference-library/upload/" className="btn btn-primary"><Plus size={14} /> Add Reference</Link>}>
              Start building your reference library by uploading your first reference document.
            </Empty>
          ) : (
            <Empty title="No references found">No references are available in the library.</Empty>
          )
        ) : (
          <DataTable rows={refs} columns={columns} rowKey={(r) => r.id} pageSize={25} searchable={false}
            onRowClick={(r) => navigate(`/content-lab-management/reference-library/${r.id}/`)} />
        )}
      </section>

      <Modal open={lockedOpen} onClose={() => setLockedOpen(false)} title={<span className="row-tight"><Lock size={15} /> Document Already Open</span>}
        footer={<button className="btn btn-primary" onClick={() => setLockedOpen(false)}>OK, Got it</button>}>
        <div className="center stack">
          <FileText size={40} className="faint" />
          <p>This document is already open in Office 365.</p>
          <p className="small muted">Please use the existing browser window to continue editing, or close it first before opening again.</p>
        </div>
      </Modal>
    </div>
  );
}
