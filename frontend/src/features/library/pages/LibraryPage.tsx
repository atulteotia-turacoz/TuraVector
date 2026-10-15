/** Port of templates/library/library.html (library.views.library_view). */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Eye, History, Lock, Search, Trash2, Upload, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { useAuth, useUser } from '@/lib/auth';
import { formatDate, formatDateTime } from '@/lib/format';
import { DataTable, ErrorNotice, Loading, PageHeader, Stat, StageStatus, useConfirm, useToast, type Column } from '@/components/ui';
import { RowMenu } from '@/features/doccore/shared';
import { STAGE_BADGE, timePart, useLibraryPage, type LibraryDocument, type LibraryResponse } from '../api';
import '../library.css';

const FILTER_KEYS = ['search', 'document_type', 'brand', 'country', 'status'] as const;
type FilterKey = typeof FILTER_KEYS[number];

export default function LibraryPage() {
  const user = useUser();
  const { can } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const applied = Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) || ''])) as Record<FilterKey, string>;
  const [form, setForm] = useState(applied);
  useEffect(() => setForm(applied), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps

  const q = useLibraryPage<LibraryResponse>(['documents'], '/api/library/documents', applied);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    FILTER_KEYS.forEach((k) => next.set(k, form[k]));
    setParams(next);
  };

  const deleteDocument = async (id: number) => {
    const ok = await confirm({
      title: 'Delete document',
      message: 'Are you sure you want to delete this document and all its versions? This action cannot be undone. Only draft documents can be deleted.',
      confirmLabel: 'Delete', danger: true,
    });
    if (!ok) return;
    try {
      const { data } = await api.delete(`/api/doccore/documents/${id}`);
      toast.success(data?.message || 'Document deleted successfully.');
    } catch (err) {
      toast.error(errorMessage(err));
    }
    void qc.invalidateQueries({ queryKey: ['library', 'documents'] });
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const data = q.data!;
  const hasFilters = !!(applied.search || applied.brand || applied.country || applied.status);

  /** Apply filters straight away (each change updates the URL, which drives the query). */
  const apply = (next: Partial<Record<FilterKey, string>>) => {
    const merged = { ...applied, ...next };
    const p = new URLSearchParams();
    FILTER_KEYS.forEach((k) => { if (merged[k]) p.set(k, merged[k]); });
    setParams(p);
  };
  const STATUS_TABS: [string, string][] = [['', 'All'], ['0', 'Draft'], ['1', 'Under review'], ['3', 'Needs revision'], ['2', 'Approved']];

  const columns: Column<LibraryDocument>[] = [
    {
      key: 'document_name', header: 'Document', value: (d) => `${d.document_name} ${d.document_number}`, render: (d) => (
        <div className="md-doc">
          <span className="md-doc-name" title={d.document_name}>{d.document_name}</span>
          <span className="md-doc-number mono">{d.document_number}</span>
          {!d.created_by_is_owner && <span className="md-sub">Created by {d.created_by_name}</span>}
        </div>
      ),
    },
    {
      key: 'document_type', header: 'Classification', value: (d) => d.document_type ?? '', render: (d) => (
        <div className="lib-class">
          <span>{d.document_type || <span className="faint">No type</span>}</span>
          <span className="md-sub">
            {[d.brand ? d.brand.name : null, d.country ? `${d.country.name} (${d.country.code_name})` : null, d.therapeutic_area]
              .filter(Boolean).join(' · ') || '—'}
          </span>
        </div>
      ),
    },
    {
      key: 'stage_status', header: 'Status', render: (d) => {
        const st = STAGE_BADGE[d.stage_status];
        return <span className="nowrap">{st ? <StageStatus label={st.label} tone={st.tone} /> : <StageStatus label="Unknown" />}</span>;
      },
    },
    {
      key: 'version_count', header: 'Versions', render: (d) => (
        <span className="nowrap">
          <span className="tnum" style={{ fontWeight: 500 }}>{d.version_count}</span>
          {d.version_count > 0 && <span className="md-sub mono">{d.first_version_number?.replace(`${d.document_number}-`, '')} latest</span>}
        </span>
      ),
    },
    {
      key: 'owner_name', header: 'Owner', render: (d) => (
        <div className="lib-owner"><span className="truncate" style={{ display: 'block' }}>{d.owner_name}</span><span className="md-sub">{d.owner_user_type}</span></div>
      ),
    },
    {
      key: 'updated_at', header: 'Updated', render: (d) => (
        <span className="nowrap">
          <span className="small">{formatDate(d.updated_at)}</span>
          <span className="md-sub">{d.modified_by_first_name !== null ? `by ${d.modified_by_first_name}` : timePart(formatDateTime(d.updated_at))}</span>
        </span>
      ),
    },
    {
      key: 'actions', header: '', sortable: false, value: () => '', render: (d) => {
        const canDeleteAny = can('can_delete_all_documents');
        const canDeleteOwn = can('can_delete_documents') && d.owner_id === user.id;
        return (
          <span className="lib-actions" onClick={(e) => e.stopPropagation()}>
            <Link to={`/content-lab-management/document/${d.id}/`} className="btn btn-secondary btn-sm" title="View Details"><Eye size={13} /><span className="lib-label">View</span></Link>
            <Link to={`/content-lab-management/document/${d.id}/history/`} className="btn btn-secondary btn-sm" title="View History"><History size={13} /><span className="lib-label">History</span></Link>
            {(canDeleteAny || canDeleteOwn) && (
              <RowMenu label={`More actions for ${d.document_number}`}>
                {(close) => (
                  <>
                    <div className="pop-head">Created {formatDate(d.created_at)} · {timePart(formatDateTime(d.created_at))}</div>
                    <div className="pop-sep" />
                    {canDeleteAny || d.stage_status === 0 ? (
                      <button className="pop-item vr-danger" onClick={() => { close(); void deleteDocument(d.id); }}>
                        <Trash2 size={14} /> {canDeleteAny ? 'Delete document' : 'Delete document (draft only)'}
                      </button>
                    ) : (
                      <button className="pop-item" disabled title="Cannot delete - Document is not in draft status"><Lock size={14} /> Delete — only drafts can be deleted</button>
                    )}
                  </>
                )}
              </RowMenu>
            )}
          </span>
        );
      },
    },
  ];

  return (
    <div className="stack-lg">
      <PageHeader title="Document Library" subtitle="Every document you can see, with its status, versions and owner."
        actions={<Link className="btn btn-primary" to="/content-lab-management/upload/"><Upload size={14} /> Upload document</Link>} />

      <div className="stat-grid">
        <Stat value={data.stats.total_documents} label="Total documents" />
        <Stat value={data.stats.review_documents} label="Under review" />
        <Stat value={data.stats.approved_documents} label="Approved" />
        <Stat value={data.stats.revised_documents} label="Needs revision" />
        <Stat value={data.stats.draft_documents} label="Draft" />
      </div>

      <section className="panel">
        <div className="md-toolbar lib-toolbar">
          <div className="filter-tabs" role="tablist" aria-label="Status">
            {STATUS_TABS.map(([v, label]) => (
              <button key={label} role="tab" aria-selected={applied.status === v} className={`filter-tab ${applied.status === v ? 'active' : ''}`}
                onClick={() => apply({ status: v })}>{label}</button>
            ))}
          </div>
          <form className="search-input lib-search" onSubmit={submit}>
            <Search size={14} />
            <input className="input" value={form.search} onChange={(e) => setForm((f) => ({ ...f, search: e.target.value }))} placeholder="Document name or number" aria-label="Search" />
          </form>
        </div>
        <div className="lib-selects">
          <select className="input" aria-label="Document type" value={applied.document_type} onChange={(e) => apply({ document_type: e.target.value })}>
            <option value="">All types</option>
            {data.document_types.map((t) => <option key={t.id} value={t.name}>{t.name}</option>)}
          </select>
          <select className="input" aria-label="Brand" value={applied.brand} onChange={(e) => apply({ brand: e.target.value })}>
            <option value="">All brands</option>
            {data.brands.map((b) => <option key={b.id} value={b.name}>{b.name}</option>)}
          </select>
          <select className="input" aria-label="Country" value={applied.country} onChange={(e) => apply({ country: e.target.value })}>
            <option value="">All countries</option>
            {data.countries.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
          <span className="lib-count small muted">{data.documents.length} document{data.documents.length === 1 ? '' : 's'}</span>
          {(hasFilters || applied.document_type) && <Link to="/content-lab-management/library/" className="btn btn-ghost btn-sm"><X size={13} /> Clear filters</Link>}
        </div>

        {data.documents.length === 0 ? (
          <div className="empty">
            <h3>No documents found</h3>
            <p>
              {hasFilters
                ? <>Try adjusting your search criteria or <Link className="act act-accent" to="/content-lab-management/library/">clear all filters</Link>.</>
                : <>Start by <Link className="act act-accent" to="/content-lab-management/upload/">uploading your first document</Link>.</>}
            </p>
          </div>
        ) : (
          <DataTable rows={data.documents} columns={columns} rowKey={(d) => d.id} pageSize={25} searchable={false}
            onRowClick={(d) => navigate(`/content-lab-management/document/${d.id}/`)} />
        )}
      </section>
    </div>
  );
}
