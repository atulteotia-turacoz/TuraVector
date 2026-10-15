import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, FileSpreadsheet, FileUp, Pencil, Plus, Search, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { Empty, ErrorNotice, Loading, PageHeader, Panel, Stat, useConfirm, useToast } from '@/components/ui';
import { CATEGORY_META, type CategoryKind, type CategoryList } from './api';
import './tools.css';

/** documents/categories/category_list.html */
export default function CategoryListPage({ kind }: { kind: CategoryKind }) {
  const meta = CATEGORY_META[kind];
  const [params, setParams] = useSearchParams();
  const search = kind === 'countries' ? params.get('search') || '' : '';
  const page = params.get('page') || undefined;
  const [draft, setDraft] = useState(search);
  useEffect(() => setDraft(search), [search]);
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();

  const q = useQuery({
    queryKey: ['tools', 'categories', kind, search, page],
    queryFn: async () => (await api.get<CategoryList>(`/api/tools/categories/${kind}`, { params: { search, page } })).data,
  });

  const toggle = async (id: number, active: boolean) => {
    const ok = await confirm({
      title: active ? 'Deactivate' : 'Activate',
      message: `Are you sure you want to ${active ? 'deactivate' : 'activate'} this ${meta.singular.toLowerCase()}?`,
      confirmLabel: active ? 'Deactivate' : 'Activate',
      danger: active,
    });
    if (!ok) return;
    try {
      const { data } = await api.post(`/api/tools/categories/${kind}/${id}/toggle`);
      toast.success(data.message);
      qc.invalidateQueries({ queryKey: ['tools', 'categories', kind] });
    } catch (e) { toast.error(errorMessage(e)); }
  };

  const go = (next: Record<string, string | undefined>) => {
    const p = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => { if (v) p.set(k, v); });
    setParams(p);
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const pg = d.pagination;

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow={d.page_title}
        title={meta.plural}
        subtitle={`Manage ${meta.plural.toLowerCase()} for document categorization`}
        actions={<>
          <Link className="btn btn-secondary" to={meta.bulkPath}><FileUp size={14} /> Bulk Import</Link>
          {kind === 'countries' && (
            <Link className="btn btn-secondary" to="/documents/categories/countries/upload/"><FileSpreadsheet size={14} /> Legacy Upload</Link>
          )}
          <Link className="btn btn-primary" to={`${meta.listPath}add/`}><Plus size={14} /> Add {meta.singular}</Link>
        </>}
      />

      <div className="grid-4">
        <Stat value={d.total_items} label={`Total ${meta.plural}`} />
        <Stat value={d.active_count} label="Active" />
        <Stat value={d.inactive_count} label="Inactive" />
        <Stat value={d.items.length ? formatDate(d.items[0].updated_at) : 'Never'} label="Last Updated" />
      </div>

      {kind === 'countries' && (
        <form className="panel panel-body row wrap" onSubmit={(e) => { e.preventDefault(); go({ search: draft.trim() || undefined }); }}>
          <div className="search-input grow" style={{ maxWidth: 'none' }}>
            <Search size={14} />
            <input className="input" name="search" placeholder="Search countries by name or code..." value={draft}
              onChange={(e) => setDraft(e.target.value)} autoFocus={!!search} />
          </div>
          <button className="btn btn-primary" type="submit"><Search size={14} /> Search</button>
          {search && <button type="button" className="btn btn-secondary" onClick={() => go({})}><X size={14} /> Clear</button>}
        </form>
      )}

      <Panel
        flush
        title={<>{meta.plural} List{search && <span className="muted small"> — Search results for “{search}”</span>}</>}
        actions={d.total_items ? <span className="small muted">{d.total_items} total {meta.plural.toLowerCase()}</span> : undefined}
        footer={pg && pg.has_pagination ? (
          <div className="between wrap">
            <span className="small muted">Showing {pg.start_index} to {pg.end_index} of {d.total_items} countries</span>
            <div className="tools-pages">
              {pg.page > 1 && <>
                <button className="btn btn-secondary btn-sm" onClick={() => go({ search, page: '1' })}>«</button>
                <button className="btn btn-secondary btn-sm" onClick={() => go({ search, page: String(pg.page - 1) })}>‹</button>
              </>}
              {Array.from({ length: pg.num_pages }, (_, i) => i + 1)
                .filter((n) => n > pg.page - 3 && n < pg.page + 3)
                .map((n) => (
                  <button key={n} className={`btn btn-secondary btn-sm ${n === pg.page ? 'is-current' : ''}`}
                    onClick={() => go({ search, page: String(n) })}>{n}</button>
                ))}
              {pg.page < pg.num_pages && <>
                <button className="btn btn-secondary btn-sm" onClick={() => go({ search, page: String(pg.page + 1) })}>›</button>
                <button className="btn btn-secondary btn-sm" onClick={() => go({ search, page: String(pg.num_pages) })}>»</button>
              </>}
            </div>
          </div>
        ) : undefined}
      >
        {d.items.length === 0 ? (
          search ? (
            <Empty title="No countries found" action={<div className="row" style={{ justifyContent: 'center' }}>
              <button className="btn btn-secondary" onClick={() => go({})}><X size={14} /> Clear Search</button>
              <Link className="btn btn-primary" to={`${meta.listPath}add/`}><Plus size={14} /> Add {meta.singular}</Link>
            </div>}>No countries match your search for “{search}”.</Empty>
          ) : (
            <Empty title={`No ${meta.plural.toLowerCase()} found`}
              action={<Link className="btn btn-primary" to={`${meta.listPath}add/`}><Plus size={14} /> Add {meta.singular}</Link>}>
              Get started by adding your first {meta.singular.toLowerCase()}.
            </Empty>
          )
        ) : (
          <div className="table-scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  {d.has_code && <th>Code</th>}
                  <th>Status</th>
                  <th>Created</th>
                  <th>Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((it) => (
                  <tr key={it.id} className={it.is_active ? '' : 'tools-row-inactive'}>
                    <td><span className="row-tight"><span className={`tools-dot ${it.is_active ? 'is-on' : ''}`} /><strong>{it.name}</strong></span></td>
                    {d.has_code && <td className="mono">{it.code_name || '-'}</td>}
                    <td>{it.is_active ? <span className="badge badge-ok">Active</span> : <span className="badge">Inactive</span>}</td>
                    <td className="small muted nowrap">{formatDateTime(it.created_at)}</td>
                    <td className="small muted nowrap">{formatDateTime(it.updated_at)}</td>
                    <td>
                      <div className="actions">
                        <Link className="btn btn-ghost btn-icon" title="Edit" to={`${meta.listPath}edit/${it.id}/`}><Pencil size={14} /></Link>
                        <button className="btn btn-ghost btn-icon" title={it.is_active ? 'Deactivate' : 'Activate'}
                          onClick={() => toggle(it.id, it.is_active)}>
                          {it.is_active ? <X size={14} /> : <Check size={14} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
