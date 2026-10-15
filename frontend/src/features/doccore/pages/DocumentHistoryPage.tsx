/** documents.document_history_view + library.document_history_view — documents/document_history.html */
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Archive, ArrowLeft, Download, Edit3, Eye, FileText, FolderOpen, History, Link2, Lock, Trash2, Upload } from 'lucide-react';
import { api, authUrl, errorMessage } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { BackLink, Badge, DataTable, ErrorNotice, Loading, PageHeader, Panel, Spinner, useConfirm, useToast, type Column } from '@/components/ui';
import { RowMenu, Stage, filesizeformat, useDocPage, useOffice365, type UserBrief } from '../shared';

interface VersionRow {
  id: number; version_number: string; file_title_name: string; file_name: string; stage_status: number; created_at: string;
  created_by: UserBrief; has_file: boolean; file_size: number | null; can_edit: boolean; delete: 'hidden' | 'any' | 'draft' | 'locked';
}
interface Single {
  mode: 'single'; page_title: string; timezone: string;
  document: { id: number; document_name: string; document_number: string; stage_status: number; owner_name: string; brand: string | null; country: string | null; created_at: string };
  versions: VersionRow[];
}
interface DocRow { id: number; document_number: string; document_name: string; stage_status: number; versions_count: number; created_at: string; updated_at: string; first_version_id: number | null }
interface All { mode: 'all'; page_title: string; documents: DocRow[] }

function timeGA(v: string) {
  return new Date(v).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

export default function DocumentHistoryPage({ source = 'documents' }: { source?: 'documents' | 'library' }) {
  const { documentId } = useParams();
  const url = documentId
    ? (source === 'library' ? `/api/doccore/library-history/${documentId}` : `/api/doccore/history/${documentId}`)
    : '/api/doccore/history';
  const q = useDocPage<Single | All>(['history', source, documentId ?? 'all'], url);
  const o365 = useOffice365();
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  return (
    <div className="stack-lg">
      {d.mode === 'single' ? <SingleHistory d={d} o365={o365} /> : <AllHistory d={d} o365={o365} />}
      {o365.popup}
    </div>
  );
}

type O365 = ReturnType<typeof useOffice365>;

function SingleHistory({ d, o365 }: { d: Single; o365: O365 }) {
  const doc = d.document;
  const confirm = useConfirm();
  const toast = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  // the newest version (highest id) is "Latest" — Django marked the oldest one
  const latestId = d.versions.reduce<number | undefined>((m, v) => (m === undefined || v.id > m ? v.id : m), undefined);
  // DataTables: order by the Created column, descending
  const rows = useMemo(() => [...d.versions].sort((a, b) => b.created_at.localeCompare(a.created_at)), [d.versions]);

  const deleteVersion = async (id: number) => {
    const ok = await confirm({
      title: 'Delete version', danger: true, confirmLabel: 'Delete',
      message: 'Are you sure you want to delete this document version? This action cannot be undone. Only draft versions can be deleted unless you have admin permissions.',
    });
    if (!ok) return;
    try {
      const { data } = await api.delete(`/api/doccore/versions/${id}`);
      toast.success(data.message);
      if (data.redirect) navigate(data.redirect);
    } catch (err: any) {
      const body = err?.response?.data;
      toast.error(body?.message || errorMessage(err));
      if (body?.redirect) navigate(body.redirect);
    }
    void qc.invalidateQueries({ queryKey: ['doccore'] });
  };

  return (
    <>
      <BackLink to={`/content-lab-management/document/${doc.id}/`}>Back to document</BackLink>
      <PageHeader eyebrow={d.page_title} title="Version history" subtitle={<>{doc.document_name} · <span className="mono">{doc.document_number}</span></>} />

      <section className="panel">
        <div className="panel-body">
          <dl className="dc-facts">
            <div><dt>Document</dt><dd>{doc.document_name}<span className="dc-sub mono">{doc.document_number}</span></dd></div>
            <div><dt>Current status</dt><dd><Stage value={doc.stage_status} revisedLabel="Revised" /></dd></div>
            <div><dt>Owner</dt><dd>{doc.owner_name}</dd></div>
            <div><dt>Brand · Country</dt><dd>{doc.brand || '-'} · {doc.country || '-'}</dd></div>
            <div><dt>Created</dt><dd>{formatDateTime(doc.created_at)}<span className="dc-sub">{d.timezone}</span></dd></div>
            <div><dt>Versions</dt><dd className="tnum">{d.versions.length}</dd></div>
          </dl>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2 className="row-tight">Versions <span className="vr-count tnum">{d.versions.length}</span></h2>
          <span className="small muted">Newest first</span>
        </div>
        {d.versions.length > 0 ? (
          <div className="table-scroll">
            <table className="tbl vr-table">
              <thead>
                <tr><th>Version</th><th>File</th><th>Status</th><th>Created</th><th className="right">Size</th><th className="right" aria-label="Actions" /></tr>
              </thead>
              <tbody>
                {rows.map((v) => {
                  const ext = (v.file_name.split('.').pop() || '').toUpperCase();
                  const latest = v.id === latestId;
                  return (
                    <tr key={v.id} className={latest ? 'vr-latest' : undefined}>
                      <td className="nowrap">
                        <span className="vr-number mono">{v.version_number}</span>
                        {latest && <span className="vr-latest-label">Latest version</span>}
                      </td>
                      <td className="vr-file-cell"><div className="vr-file">
                        <span className="vr-ext">{ext.length <= 5 ? ext : 'FILE'}</span>
                        <span style={{ minWidth: 0 }}>
                          <span className="vr-title" title={v.file_title_name}>{v.file_title_name}</span>
                          {v.file_name !== v.file_title_name && <span className="vr-sub">{v.file_name}</span>}
                        </span>
                      </div></td>
                      <td className="nowrap"><Stage value={v.stage_status} /></td>
                      <td className="vr-created">
                        <span className="small nowrap">{formatDate(v.created_at)} · {timeGA(v.created_at)}</span>
                        <span className="vr-sub">by {v.created_by.first_name} {v.created_by.last_name}{v.created_by.user_type_title ? ` · ${v.created_by.user_type_title}` : ''}</span>
                      </td>
                      <td className="right nowrap small tnum">{v.has_file ? filesizeformat(v.file_size) : <span className="faint">—</span>}</td>
                      <td className="right">
                        <span className="vr-actions">
                          <Link className="btn btn-secondary btn-sm" title="Preview" to={`/content-lab-management/preview/${v.id}/`}><Eye size={13} /><span className="vr-label">Preview</span></Link>
                          {v.can_edit && <Link className="btn btn-secondary btn-sm" title="Edit" to={`/content-lab-management/editor/${v.id}/`}><Edit3 size={13} /><span className="vr-label">Edit</span></Link>}
                          <RowMenu label={`More actions for ${v.version_number}`}>
                            {(close) => (
                              <>
                                {v.has_file && <a className="pop-item" target="_blank" rel="noreferrer" href={authUrl(`/api/doccore/versions/${v.id}/file`)} onClick={close}><Download size={14} /> Download</a>}
                                <button className="pop-item" disabled={o365.busy === v.id} onClick={() => { close(); void o365.open(v.id); }}>
                                  {o365.busy === v.id ? <Spinner /> : <FileText size={14} />} Open in Office 365
                                </button>
                                <Link className="pop-item" to={`/content-lab-management/version/${v.id}/link-references/`} onClick={close}><Link2 size={14} /> Link references</Link>
                                {v.delete !== 'hidden' && <div className="pop-sep" />}
                                {(v.delete === 'any' || v.delete === 'draft') && (
                                  <button className="pop-item vr-danger" onClick={() => { close(); void deleteVersion(v.id); }}>
                                    <Trash2 size={14} /> {v.delete === 'draft' ? 'Delete version (draft only)' : 'Delete version'}
                                  </button>
                                )}
                                {v.delete === 'locked' && <button className="pop-item" disabled title="Cannot delete - Version is not in draft status"><Lock size={14} /> Delete — only drafts can be deleted</button>}
                              </>
                            )}
                          </RowMenu>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty"><FileText size={32} className="faint" /><h3>No versions available</h3><p>No versions have been created for this document yet.</p></div>
        )}
      </section>
    </>
  );
}

function AllHistory({ d, o365 }: { d: All; o365: O365 }) {
  const rows = useMemo(() => [...d.documents].sort((a, b) => b.versions_count - a.versions_count), [d.documents]);
  const columns: Column<DocRow>[] = [
    { key: 'document_number', header: 'Document Number', render: (r) => <strong>{r.document_number}</strong> },
    { key: 'document_name', header: 'Document Name' },
    { key: 'stage_status', header: 'Status', render: (r) => <Stage value={r.stage_status} revisedLabel="Revised" /> },
    { key: 'versions_count', header: 'Versions', render: (r) => <Badge tone="accent">{r.versions_count}</Badge> },
    { key: 'created_at', header: 'Created', render: (r) => formatDate(r.created_at) },
    { key: 'updated_at', header: 'Last Modified', render: (r) => formatDate(r.updated_at) },
    {
      key: 'actions', header: 'Actions', sortable: false, value: () => '', render: (r) => (
        <span className="dc-btn-group">
          <Link className="btn btn-secondary btn-sm btn-icon" title="View Details" to={`/content-lab-management/document/${r.id}/`}><Eye size={14} /></Link>
          <Link className="btn btn-secondary btn-sm btn-icon" title="View History" to={`/content-lab-management/history/${r.id}/`}><History size={14} /></Link>
          {r.first_version_id && (
            <button type="button" className="btn btn-secondary btn-sm btn-icon" title="Open in Office 365" disabled={o365.busy === r.first_version_id}
              onClick={() => void o365.open(r.first_version_id!)}>
              {o365.busy === r.first_version_id ? <Spinner /> : <FileText size={14} />}
            </button>
          )}
        </span>
      ),
    },
  ];
  return (
    <>
      <PageHeader eyebrow={d.page_title} title={<span className="row-tight"><History size={20} className="dc-accent" /> All Documents History</span>} />
      <Panel flush>
        {d.documents.length > 0
          ? <DataTable rows={rows} columns={columns} rowKey={(r) => r.id} />
          : (
            <div className="empty">
              <FolderOpen size={32} className="faint" />
              <h3>No documents found</h3>
              <p>You haven't created any documents yet.</p>
              <div style={{ marginTop: 12 }}><Link className="btn btn-primary" to="/content-lab-management/upload/"><Upload size={14} /> Upload First Document</Link></div>
            </div>
          )}
      </Panel>
    </>
  );
}
