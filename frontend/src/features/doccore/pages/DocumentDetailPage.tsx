/** document_detail — documents/document_detail.html */
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, Clock, Download, Edit3, Eye, FileText, FolderKanban, History, Lock, Plus,
  RefreshCw, Trash2, Upload, User, UserPlus, Users, UsersRound,
} from 'lucide-react';
import { api, authUrl, errorMessage } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { Badge, ErrorNotice, Loading, PageHeader, Panel, Spinner, Stat, useConfirm, useToast } from '@/components/ui';
import { RowMenu, Stage, useDocPage, useOffice365, type UserBrief } from '../shared';

interface VersionRow {
  id: number; version_number: string; file_title_name: string; file_name: string; file_extension: string;
  stage_status: number; created_at: string; created_by: UserBrief; has_file: boolean; shared_count: number;
  edit: 'hidden' | 'link' | 'locked_review' | 'locked_approved'; delete: 'hidden' | 'any' | 'draft' | 'locked';
}
interface Data {
  document: {
    id: number; document_name: string; document_number: string; stage_status: number; document_type: string | null;
    brand: { name: string; code_name: string } | null; country: { name: string; code_name: string } | null;
    therapeutic_area: string | null; course: string | null; owner: UserBrief; created_by: UserBrief; created_by_is_owner: boolean;
    modified_by: UserBrief | null; created_at: string; updated_at: string; days_since_created: number; project_status: string | null;
  };
  timezone: string;
  latest_version: { id: number; version_number: string } | null;
  latest_version_status: number; has_approved_version: boolean;
  versions: VersionRow[];
  flags: {
    is_owner: boolean; show_version_actions: boolean; show_reviewer_actions: boolean; show_update_status: boolean;
    show_edit_details: boolean; edit_details_state: 'link' | 'locked_review' | 'locked_approved';
    show_collaborators_column: boolean; can_manage_collaborators: boolean; upload_first_version: boolean;
  };
}

function time24(v: string) {
  return new Date(v).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

export default function DocumentDetailPage() {
  const { documentId } = useParams();
  const q = useDocPage<Data>(['detail', documentId], `/api/doccore/documents/${documentId}`);
  const o365 = useOffice365();
  const confirm = useConfirm();
  const toast = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [syncItems, setSyncItems] = useState<Record<number, string>>({});
  const [actionItem, setActionItem] = useState<string | null>(null);
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const doc = d.document;
  const f = d.flags;
  const lvs = d.latest_version_status;

  const deleteVersion = async (id: number) => {
    const ok = await confirm({
      title: 'Delete version', danger: true, confirmLabel: 'Delete',
      message: 'Are you sure you want to delete this document version? This action cannot be undone. Only draft versions can be deleted and the document must have multiple versions.',
    });
    if (!ok) return;
    try {
      const { data } = await api.delete(`/api/doccore/versions/${id}`);
      toast.success(data.message);
      if (data.redirect && data.redirect !== location.pathname) navigate(data.redirect);
    } catch (err: any) {
      const body = err?.response?.data;
      toast.error(body?.message || errorMessage(err));
      if (body?.redirect && body.redirect !== location.pathname) navigate(body.redirect);
    }
    void qc.invalidateQueries({ queryKey: ['doccore'] });
  };

  const openAction = async () => {
    if (!d.latest_version) return;
    const item = await o365.open(d.latest_version.id);
    if (item) setActionItem(item);
  };
  const openRow = async (id: number) => {
    const item = await o365.open(id);
    if (item) setSyncItems((s) => ({ ...s, [id]: item }));
  };

  return (
    <div className="stack-lg">
      <PageHeader eyebrow="Document Details"
        title={<span className="row-tight"><FileText size={20} className="dc-accent" /> {doc.document_name}</span>}
        actions={<Stage value={lvs} />} />

      <Panel>
        <div className="grid-2">
          <dl className="kv">
            <dt>Document Number:</dt><dd><strong>{doc.document_number}</strong></dd>
            <dt>Document Type:</dt><dd>{doc.document_type ? <Badge tone="accent">{doc.document_type}</Badge> : <span className="muted">-</span>}</dd>
            <dt>Brand:</dt><dd>{doc.brand ? <><strong>{doc.brand.name}</strong> <span className="small muted">({doc.brand.code_name})</span></> : <span className="muted">-</span>}</dd>
            <dt>Country:</dt><dd>{doc.country ? <>{doc.country.name} <span className="small muted">({doc.country.code_name})</span></> : <span className="muted">-</span>}</dd>
            <dt>Therapeutic Area:</dt><dd>{doc.therapeutic_area ? <Badge tone="ok">{doc.therapeutic_area}</Badge> : <span className="muted">-</span>}</dd>
          </dl>
          <dl className="kv">
            <dt>Course:</dt><dd>{doc.course || <span className="muted">-</span>}</dd>
            <dt>Owner:</dt><dd><strong>{doc.owner.first_name} {doc.owner.last_name}</strong><span className="dc-sub">{doc.owner.user_type_title}</span></dd>
            <dt>Created:</dt>
            <dd>
              {formatDateTime(doc.created_at)} <span className="small muted">({d.timezone})</span>
              {!doc.created_by_is_owner && <span className="dc-sub">by {doc.created_by.first_name} {doc.created_by.last_name}</span>}
            </dd>
            <dt>Last Modified:</dt>
            <dd>
              {formatDateTime(doc.updated_at)} <span className="small muted">({d.timezone})</span>
              {doc.modified_by && <span className="dc-sub">by {doc.modified_by.first_name} {doc.modified_by.last_name}</span>}
            </dd>
          </dl>
        </div>
      </Panel>

      <Panel title="Document Actions">
        <div className="dc-actions">
          <Link className="btn btn-secondary" to={`/content-lab-management/history/${doc.id}/`}><History size={14} /> View History</Link>
          {f.show_version_actions && (
            !d.has_approved_version && lvs !== 1
              ? <Link className="btn btn-primary" to={`/content-lab-management/document/${doc.id}/new-version/`}><Plus size={14} /> New Version</Link>
              : lvs === 1
                ? <button className="btn btn-secondary" disabled title="Cannot create new version - Document is under review"><Lock size={14} /> Under Review</button>
                : <button className="btn btn-secondary" disabled title="Cannot create new version - Document has approved version"><Lock size={14} /> Version Locked</button>
          )}
          {f.show_reviewer_actions && (
            <>
              {d.versions.length > 0
                ? (!d.has_approved_version
                  ? <Link className="btn btn-secondary" to={`/content-lab-management/document/${doc.id}/assign-reviewer/`}><UserPlus size={14} /> Assign Reviewer</Link>
                  : <button className="btn btn-secondary" disabled title="Cannot assign reviewer - Document has approved version"><Lock size={14} /> Reviewer Locked</button>)
                : <button className="btn btn-secondary" disabled title="No versions available"><UserPlus size={14} /> Assign Reviewer</button>}
              <Link className="btn btn-secondary" to={`/content-lab-management/document/${doc.id}/manage-reviewers/`}><Users size={14} /> Manage Reviewers</Link>
            </>
          )}
          {f.show_edit_details && (
            f.edit_details_state === 'link'
              ? <Link className="btn btn-secondary" to={`/content-lab-management/document/${doc.id}/edit/`}><Edit3 size={14} /> Edit Details</Link>
              : f.edit_details_state === 'locked_review'
                ? <button className="btn btn-secondary" disabled title="Cannot edit - Document is under review"><Lock size={14} /> Under Review</button>
                : <button className="btn btn-secondary" disabled title="Cannot edit - Document has approved version"><Lock size={14} /> Edit Locked</button>
          )}
          {d.latest_version && (
            <>
              <button type="button" className="btn btn-secondary" title="Open latest version in Office 365"
                disabled={o365.busy === d.latest_version.id} onClick={() => void openAction()}>
                {o365.busy === d.latest_version.id ? <Spinner label="Uploading..." /> : <><FileText size={14} /> Open in Office 365</>}
              </button>
              {actionItem && (
                <button type="button" className="btn btn-secondary" title="Sync Back from Office 365"
                  onClick={async () => { if (await o365.sync(d.latest_version!.id, actionItem)) setActionItem(null); }}>
                  <RefreshCw size={14} /> Sync Back
                </button>
              )}
            </>
          )}
          <Link className="btn btn-ghost" to="/content-lab-management/library/"><ArrowLeft size={14} /> Back to Library</Link>
        </div>
      </Panel>

      <section className="panel">
        <div className="panel-head">
          <h2 className="row-tight">Versions <span className="vr-count tnum">{d.versions.length}</span></h2>
        </div>
        {d.versions.length > 0 ? (
          <div className="table-scroll">
            <table className="tbl vr-table">
              <thead>
                <tr>
                  <th>Version</th><th>File</th><th>Status</th><th>Created</th>
                  {f.show_collaborators_column && <th>Collaborators</th>}
                  <th className="right" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {d.versions.map((v, i) => {
                  const ext = (v.file_extension || '').toUpperCase();
                  const editLockReason = v.edit === 'locked_review' ? 'Cannot edit - Document is under review'
                    : v.edit === 'locked_approved' ? 'Cannot edit - Document has approved version' : '';
                  return (
                    <tr key={v.id} className={i === 0 ? 'vr-latest' : undefined}>
                      <td className="nowrap">
                        <span className="vr-number mono">{v.version_number}</span>
                        {i === 0 && <span className="vr-latest-label">Latest version</span>}
                      </td>
                      <td className="vr-file-cell"><div className="vr-file">
                        <span className="vr-ext" aria-label={`${ext} file`}>{ext || 'FILE'}</span>
                        <span style={{ minWidth: 0 }}>
                          <span className="vr-title" title={v.file_title_name}>{v.file_title_name}</span>
                          {v.file_name !== v.file_title_name && <span className="vr-sub">{v.file_name}</span>}
                          {!v.has_file && <span className="vr-sub" style={{ color: 'var(--danger)' }}>File not available</span>}
                        </span>
                      </div></td>
                      <td className="nowrap"><Stage value={v.stage_status} /></td>
                      <td className="vr-created">
                        <span className="small nowrap">{formatDate(v.created_at)} · {time24(v.created_at)}</span>
                        <span className="vr-sub">by {v.created_by.first_name} {v.created_by.last_name}{v.created_by.user_type_title ? ` · ${v.created_by.user_type_title}` : ''}</span>
                      </td>
                      {f.show_collaborators_column && (
                        <td className="nowrap">
                          {f.can_manage_collaborators
                            ? <Link className="act vr-share" title="Manage Version Collaborators" to={`/content-lab-management/version/${v.id}/collaborators/`}>
                                <UsersRound size={13} /> {v.shared_count > 0 ? `${v.shared_count} shared` : 'Share'}
                              </Link>
                            : <span className="faint">—</span>}
                        </td>
                      )}
                      <td className="right">
                        <span className="vr-actions">
                          <Link className="btn btn-secondary btn-sm" title="Preview" to={`/content-lab-management/preview/${v.id}/`}><Eye size={13} /><span className="vr-label">Preview</span></Link>
                          {v.edit === 'link' && <Link className="btn btn-secondary btn-sm" title="Edit" to={`/content-lab-management/editor/${v.id}/`}><Edit3 size={13} /><span className="vr-label">Edit</span></Link>}
                          {editLockReason && <button className="btn btn-secondary btn-sm" disabled title={editLockReason}><Lock size={13} /><span className="vr-label">Edit</span></button>}
                          <RowMenu label={`More actions for ${v.version_number}`}>
                            {(close) => (
                              <>
                                {v.has_file
                                  ? <a className="pop-item" target="_blank" rel="noreferrer" href={authUrl(`/api/doccore/versions/${v.id}/file`)} onClick={close}><Download size={14} /> Download original</a>
                                  : <button className="pop-item" disabled title="No file available"><Download size={14} /> Download original</button>}
                                <button className="pop-item" disabled={o365.busy === v.id} onClick={() => { close(); void openRow(v.id); }}>
                                  {o365.busy === v.id ? <Spinner /> : <FileText size={14} />} Open in Office 365
                                </button>
                                {syncItems[v.id] && (
                                  <button className="pop-item" onClick={async () => { close(); if (await o365.sync(v.id, syncItems[v.id])) setSyncItems((s) => { const n = { ...s }; delete n[v.id]; return n; }); }}>
                                    <RefreshCw size={14} /> Sync back from Office 365
                                  </button>
                                )}
                                {v.delete !== 'hidden' && <div className="pop-sep" />}
                                {(v.delete === 'any' || v.delete === 'draft') && (
                                  <button className="pop-item vr-danger" onClick={() => { close(); void deleteVersion(v.id); }}>
                                    <Trash2 size={14} /> {v.delete === 'draft' ? 'Delete version (draft only)' : 'Delete version'}
                                  </button>
                                )}
                                {v.delete === 'locked' && (
                                  <button className="pop-item" disabled title="Cannot delete - Version is not in draft status"><Lock size={14} /> Delete — only drafts can be deleted</button>
                                )}
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
          <div className="empty">
            <FileText size={32} className="faint" />
            <h3>No versions available</h3>
            <p>Upload the first version of this document to get started.</p>
            {f.upload_first_version && (
              <div className="stack" style={{ alignItems: 'center', marginTop: 12 }}>
                <Link className="btn btn-primary" to={`/content-lab-management/document/${doc.id}/new-version/`}><Upload size={14} /> Upload First Version</Link>
                {f.is_owner && <span className="small muted">You can create multiple versions of this document as needed</span>}
              </div>
            )}
          </div>
        )}
      </section>

      <div className="stat-grid">
        <Stat value={d.versions.length} label={<span className="row-tight"><FileText size={13} /> Total Versions</span>} />
        <Stat value={doc.days_since_created} label={<span className="row-tight"><Clock size={13} /> Days Since Created</span>} />
        <Stat value={doc.owner.first_name || ' '} label={<span className="row-tight"><User size={13} /> Document Owner</span>} />
        <Stat value={doc.project_status || 'No Project'} label={<span className="row-tight"><FolderKanban size={13} /> Project Status</span>} />
      </div>
      {o365.popup}
    </div>
  );
}
