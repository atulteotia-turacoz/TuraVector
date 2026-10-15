import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Eye, Key, KeyRound, Pencil, Plus, Search, Shield, SlidersHorizontal, UserCheck, UserX } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { API, formErrors, useIndex, useModelConfig, type ChangeList as CL, type DeleteSummary, type FilterChoice, type Message } from '@/lib/admin';
import { ErrorNotice, Loading, PageHeader, Panel, useToast } from '@/components/ui';
import { Crumbs, ScopeBanner } from '@/components/Shell';
import { CellView, FieldInput } from '@/components/fields';
import { DeleteSummaryView } from '@/components/DeleteSummary';

function capfirst(s: string) { return s ? s[0].toUpperCase() + s.slice(1) : s; }

export function toastMessages(toast: ReturnType<typeof useToast>, msgs: Message[] | undefined) {
  (msgs || []).forEach((m) => {
    if (m.level === 'error') toast.error(m.message);
    else if (m.level === 'warning') toast.warning(m.message);
    else if (m.level === 'success') toast.success(m.message);
    else toast.info(m.message);
  });
}

function pageNumbers(page: number, pages: number): (number | '…')[] {
  // Django's get_elided_page_range(on_each_side=3, on_ends=2)
  if (pages <= 10) return Array.from({ length: pages }, (_, i) => i + 1);
  const out: (number | '…')[] = [];
  const add = (a: number, b: number) => { for (let i = a; i <= b; i++) out.push(i); };
  if (page > 1 + 3 + 2 + 1) { add(1, 2); out.push('…'); add(page - 3, page); } else add(1, page);
  if (page < pages - 3 - 2 - 1) { add(page + 1, page + 3); out.push('…'); add(pages - 1, pages); } else add(page + 1, pages);
  return out;
}

/** View / edit / permissions / passwords / (de)activate — the user management pages for one user. */
function UserRowActions({ pk, active, onToggled }: { pk: string; active: boolean; onToggled: () => void }) {
  const toast = useToast();
  const toggle = async () => {
    if (!window.confirm(`Are you sure you want to ${active ? 'deactivate' : 'activate'} this user?`)) return;
    try {
      const { data } = await api.post(`/api/users/${pk}/toggle-status`);
      toast.success(data.message);
      onToggled();
    } catch (err) { toast.error(errorMessage(err)); }
  };
  return (
    <div className="row-tight nowrap">
      <Link className="btn btn-ghost btn-icon" title="View Profile" to={`/library/user/${pk}/view/`}><Eye size={14} /></Link>
      <Link className="btn btn-ghost btn-icon" title="Edit User" to={`/library/user/${pk}/edit/`}><Pencil size={14} /></Link>
      <Link className="btn btn-ghost btn-icon" title="Manage Permissions" to={`/library/user/${pk}/permissions/`}><Shield size={14} /></Link>
      <Link className="btn btn-ghost btn-icon" title="Change Password" to={`/library/user/${pk}/change-password/`}><Key size={14} /></Link>
      <Link className="btn btn-ghost btn-icon" title="View Password" to={`/library/user/${pk}/view-password/`}><KeyRound size={14} /></Link>
      <button type="button" className="btn btn-ghost btn-icon" title={active ? 'Deactivate' : 'Activate'} onClick={toggle}>
        {active ? <UserX size={14} /> : <UserCheck size={14} />}</button>
    </div>
  );
}

export default function ChangeList() {
  const { app = '', model = '' } = useParams();
  return <ChangeListView app={app} model={model} />;
}

/** Search / filter / page state: in the URL for the full page, in memory when embedded in a tab. */
function useListParams(embedded: boolean): [URLSearchParams, (n: URLSearchParams) => void] {
  const [urlSp, setUrlSp] = useSearchParams();
  const [localSp, setLocalSp] = useState(() => new URLSearchParams());
  return embedded ? [localSp, setLocalSp] : [urlSp, setUrlSp];
}

/**
 * A model's change list. `workspace` limits a workspace-level model to one organisation (used by the
 * tabs of an organisation's page); `embedded` drops the page chrome so it fits inside a tab.
 */
export function ChangeListView({ app, model, workspace, embedded = false }: {
  app: string; model: string; workspace?: number; embedded?: boolean;
}) {
  const index = useIndex();
  const modelScope = index.data?.apps.flatMap((a) => a.models).find((m) => m.app === app && m.model === model)?.scope;
  const [sp, setSp] = useListParams(embedded);
  const params = useMemo(() => Object.fromEntries(sp.entries()), [sp]);
  const ws = workspace ? { workspace: String(workspace) } : {};
  const toast = useToast();
  const qc = useQueryClient();
  const cfg = useModelConfig(app, model);
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['admin', 'cl', app, model, params, workspace ?? null],
    queryFn: async () => (await api.get<CL>(`${API}/models/${app}/${model}/`, { params: { ...params, ...ws } })).data,
    placeholderData: (prev) => prev,
  });
  const [q, setQ] = useState(params.q || '');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [across, setAcross] = useState(false);
  const [action, setAction] = useState('');
  const [busy, setBusy] = useState(false);
  const [edits, setEdits] = useState<Record<string, Record<string, any>>>({});
  const [rowErrors, setRowErrors] = useState<Record<string, Record<string, string[]>>>({});
  const [confirm, setConfirm] = useState<{ ids: string[]; summary: DeleteSummary } | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => { setQ(params.q || ''); setSelected(new Set()); setAcross(false); setEdits({}); setRowErrors({}); }, [app, model, params.q]);
  useEffect(() => { setSelected(new Set()); setAcross(false); }, [sp]);

  if (isLoading || cfg.isLoading) return <Loading />;
  if (error) return <ErrorNotice error={error} />;
  if (cfg.error) return <ErrorNotice error={cfg.error} />;
  const d = data!;
  const c = cfg.data!;

  const update = (next: Record<string, string | undefined>, resetPage = true) => {
    const n = new URLSearchParams(sp);
    Object.entries(next).forEach(([k, v]) => (v === undefined || v === '' ? n.delete(k) : n.set(k, v)));
    if (resetPage) n.delete('p');
    setSp(n);
  };
  const applyChoice = (keys: string[], choice: FilterChoice) => {
    const n = new URLSearchParams(sp);
    keys.forEach((k) => n.delete(k));
    Object.entries(choice.params).forEach(([k, v]) => n.set(k, v));
    n.delete('p');
    setSp(n);
  };
  const sortBy = (index: number) => {
    const cur = d.ordering[0];
    const desc = cur && cur.index === index ? !cur.desc : false;
    update({ o: `${desc ? '-' : ''}${index}` });
  };
  const allOnPage = d.rows.length > 0 && d.rows.every((r) => selected.has(r.pk));
  const toggleAll = () => { setAcross(false); setSelected(allOnPage ? new Set() : new Set(d.rows.map((r) => r.pk))); };
  const toggle = (pk: string) => {
    setAcross(false);
    setSelected((s) => { const n = new Set(s); n.has(pk) ? n.delete(pk) : n.add(pk); return n; });
  };

  const runAction = async (post = false, ids?: string[]) => {
    setBusy(true);
    try {
      const { data: res } = await api.post(`${API}/models/${app}/${model}/action`, {
        action: post ? 'delete_selected' : action, ids: ids ?? Array.from(selected), select_across: post ? false : across, params, post,
      }, { params: ws });
      if (res.confirm) { setConfirm({ ids: res.ids, summary: res.summary }); return; }
      toastMessages(toast, res.messages);
      setConfirm(null);
      setSelected(new Set()); setAcross(false);
      void qc.invalidateQueries({ queryKey: ['admin'] });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const saveEdits = async (e: FormEvent) => {
    e.preventDefault();
    const rows = Object.entries(edits).map(([pk, values]) => ({ pk, values }));
    if (!rows.length) return;
    setBusy(true);
    try {
      const { data: res } = await api.post(`${API}/models/${app}/${model}/list-edit`, { rows }, { params: ws });
      if (res.message) toast.success(res.message);
      setEdits({}); setRowErrors({});
      void qc.invalidateQueries({ queryKey: ['admin'] });
    } catch (err) {
      const fe = formErrors(err);
      if (fe?.row_errors) { setRowErrors(fe.row_errors); toast.error(fe.message || 'Please correct the errors below.'); }
      else toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const crumbs = [{ label: c.app_name, to: `/${app}/` }, { label: capfirst(d.verbose_name_plural) }];

  if (confirm) {
    const plural = d.verbose_name_plural;
    return (
      <>
        <Crumbs items={[...crumbs.slice(0, 1), { label: capfirst(plural), to: `/${app}/${model}/` }, { label: 'Delete multiple objects' }]} />
        <PageHeader title="Are you sure?" />
        <Panel>
          <DeleteSummaryView summary={confirm.summary}
            intro={`Are you sure you want to delete the selected ${plural}? All of the following objects and their related items will be deleted:`}
            protectedIntro={`Deleting the selected ${plural} would require deleting the following protected related objects:`} />
        </Panel>
        <div className="submit-row">
          {!confirm.summary.protected.length && (
            <button className="btn btn-danger" disabled={busy} onClick={() => runAction(true, confirm.ids)}>Yes, I’m sure</button>
          )}
          <button className="btn btn-secondary" onClick={() => setConfirm(null)}>No, take me back</button>
        </div>
      </>
    );
  }

  const filtered = d.count !== d.full_count;
  // the users list gets the same per-user actions as All Users
  const isUsers = app === 'authentication' && model === 'user';
  const activeIdx = d.columns.findIndex((col) => col.name === 'is_active');
  const activeFilters = d.filters.filter((f) => f.keys.some((k) => sp.has(k))).length;
  const editable = c.list_editable;
  return (
    <>
      {embedded ? (
        <div className="cl-embedded-head">
          <h2>{capfirst(d.verbose_name_plural)}</h2>
          {c.perms.add && <Link className="btn btn-primary btn-sm" to={`/${app}/${model}/add/`}><Plus size={14} /> Add {d.verbose_name}</Link>}
        </div>
      ) : (
        <>
          <Crumbs items={crumbs} />
          <PageHeader title={`Select ${d.verbose_name} to ${c.perms.change ? 'change' : 'view'}`}
            actions={c.perms.add && <Link className="btn btn-primary" to={`/${app}/${model}/add/`}><Plus size={14} /> Add {d.verbose_name}</Link>} />
          {modelScope && <ScopeBanner scope={modelScope} />}
        </>
      )}
      <div className={`cl-layout ${d.filters.length && showFilters ? '' : 'no-filter'}`}>
        <form className="panel" onSubmit={saveEdits}>
          {(d.search_enabled || d.filters.length > 0) && (
            <div className="cl-toolbar">
              {d.search_enabled && <>
              <div className="search-input" role="search">
                <Search size={14} />
                <input className="input" aria-label={`Search ${d.verbose_name_plural}`} value={q} placeholder="Search…"
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); update({ q: q.trim() || undefined }); } }} />
              </div>
              <button type="button" className="btn btn-secondary" onClick={() => update({ q: q.trim() || undefined })}>Search</button>
              </>}
              {d.filters.length > 0 && (
                // the filter panel takes room from the table, so it opens on demand
                <button type="button" className={`btn ${showFilters ? 'btn-primary' : 'btn-secondary'} cl-filter-toggle`}
                  aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
                  <SlidersHorizontal size={14} /> Filters{activeFilters > 0 && <span className="cl-filter-count">{activeFilters}</span>}
                </button>
              )}
              {filtered && (
                <span className="small muted">
                  {d.count} result{d.count === 1 ? '' : 's'} (<button type="button" className="act" onClick={() => setSp(new URLSearchParams())}>{d.full_count} total</button>)
                </span>
              )}
              {isFetching && <span className="spinner" aria-label="Loading" />}
            </div>
          )}
          {d.date_hierarchy && (
            <div className="date-hier" aria-label={`Filter by ${d.date_hierarchy.title}`}>
              {d.date_hierarchy.back && <button type="button" onClick={() => applyChoice(d.date_hierarchy!.keys, d.date_hierarchy!.back!)}>‹ {d.date_hierarchy.back.label}</button>}
              {d.date_hierarchy.choices.map((ch, i) => ch.selected
                ? <strong key={i} className="small">{ch.label}</strong>
                : <button type="button" key={i} onClick={() => applyChoice(d.date_hierarchy!.keys, ch)}>{ch.label}</button>)}
            </div>
          )}
          {d.actions.length > 0 && (
            <div className="cl-actions">
              <label className="row-tight small">
                <span className="muted">Action:</span>
                <select className="input" value={action} onChange={(e) => setAction(e.target.value)}>
                  <option value="">---------</option>
                  {d.actions.map((a) => <option key={a.name} value={a.name}>{a.description}</option>)}
                </select>
              </label>
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => runAction(false)}>Go</button>
              <span className="small muted">
                {across ? `All ${d.count} selected` : `${selected.size} of ${d.rows.length} selected`}
              </span>
              {allOnPage && !across && d.count > d.rows.length && (
                <button type="button" className="act act-accent small" onClick={() => setAcross(true)}>Select all {d.count} {d.verbose_name_plural}</button>
              )}
              {across && <button type="button" className="act small" onClick={() => { setAcross(false); setSelected(new Set()); }}>Clear selection</button>}
            </div>
          )}
          <div className="table-scroll">
            <table className="tbl cl-table">
              <thead>
                <tr>
                  {d.actions.length > 0 && (
                    <th className="check"><input type="checkbox" aria-label="Select all objects on this page" checked={allOnPage} onChange={toggleAll} /></th>
                  )}
                  {d.columns.map((col) => {
                    const ord = d.ordering.find((o) => o.index === col.index);
                    return (
                      <th key={col.index} scope="col" className={`${col.sortable ? 'sortable' : ''} ${ord ? 'sorted' : ''}`}
                        onClick={col.sortable ? () => sortBy(col.index) : undefined}
                        aria-sort={ord ? (ord.desc ? 'descending' : 'ascending') : undefined}>
                        {col.label}{ord && <span className="sort-ind">{ord.desc ? '↓' : '↑'}</span>}
                      </th>
                    );
                  })}
                  {isUsers && <th scope="col">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {d.rows.length === 0 && (
                  <tr><td colSpan={d.columns.length + 2}><div className="empty small">0 {d.verbose_name_plural}</div></td></tr>
                )}
                {d.rows.map((r) => (
                  <tr key={r.pk} className={selected.has(r.pk) || across ? 'selected' : ''}>
                    {d.actions.length > 0 && (
                      <td className="check"><input type="checkbox" aria-label={`Select ${r.str}`} checked={across || selected.has(r.pk)} onChange={() => toggle(r.pk)} /></td>
                    )}
                    {d.columns.map((col, i) => {
                      const cellEl = (
                        <CellView cell={r.cells[i]}
                          changeFileTo={r.cells[i]?.route === 'change_file' ? `/${app}/${model}/${encodeURIComponent(r.pk)}/change-file/` : undefined} />
                      );
                      if (col.editable && c.editable_fields[col.name]) {
                        const err = rowErrors[r.pk]?.[col.name];
                        const val = edits[r.pk]?.[col.name] ?? r.values[col.name];
                        return (
                          <td key={col.index} className={err ? 'err' : ''}>
                            <FieldInput meta={c.editable_fields[col.name]} value={val} app={app} model={model}
                              onChange={(v) => setEdits((e) => ({ ...e, [r.pk]: { ...(e[r.pk] || {}), [col.name]: v } }))} invalid={!!err} />
                            {err && <div className="field-error">{err.join(' ')}</div>}
                          </td>
                        );
                      }
                      return (
                        <td key={col.index}>
                          {i === 0
                            ? <Link className="act" style={{ fontWeight: 500 }} to={`/${app}/${model}/${encodeURIComponent(r.pk)}/change/`}>{r.cells[0]?.text ?? cellEl}</Link>
                            : cellEl}
                        </td>
                      );
                    })}
                    {isUsers && (
                      <td className="cl-row-actions">
                        <UserRowActions pk={r.pk} active={activeIdx >= 0 ? r.cells[activeIdx]?.bool !== false : true}
                          onToggled={() => void qc.invalidateQueries({ queryKey: ['admin'] })} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination between">
            <div className="pages">
              {!d.show_all && d.pages > 1 && pageNumbers(d.page, d.pages).map((p, i) => p === '…'
                ? <span key={`e${i}`} className="faint">…</span>
                : <button type="button" key={p} className={`btn btn-secondary btn-sm ${p === d.page ? 'current' : ''}`} aria-current={p === d.page ? 'page' : undefined}
                  onClick={() => update({ p: String(p) }, false)}>{p}</button>)}
              <span className="small muted" style={{ marginLeft: 6 }}>{d.count} {d.count === 1 ? d.verbose_name : d.verbose_name_plural}</span>
              {d.can_show_all && !d.show_all && <button type="button" className="act small" style={{ marginLeft: 8 }} onClick={() => update({ all: '1' }, true)}>Show all</button>}
            </div>
            {editable.length > 0 && <button className="btn btn-primary btn-sm" disabled={busy || Object.keys(edits).length === 0}>Save</button>}
          </div>
        </form>
        {d.filters.length > 0 && showFilters && (
          <aside className="panel cl-filter" aria-label="Filter">
            <div className="panel-head"><h2>Filter</h2>
              {d.filters.some((f) => f.keys.some((k) => sp.has(k))) && (
                <button className="act small" onClick={() => { const n = new URLSearchParams(); if (params.q) n.set('q', params.q); setSp(n); }}>Clear all filters</button>
              )}
            </div>
            <div className="panel-body">
              {d.filters.map((f) => (
                <div key={f.path} className="filter-block">
                  <div className="filter-title">By {f.title}</div>
                  <ul className="filter-list">
                    {f.choices.map((ch, i) => (
                      <li key={i}><button className={ch.selected ? 'on' : ''} aria-pressed={!!ch.selected} onClick={() => applyChoice(f.keys, ch)}>{ch.label}</button></li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </aside>
        )}
      </div>
    </>
  );
}
