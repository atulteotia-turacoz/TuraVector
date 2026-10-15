/**
 * Shared UI vocabulary. Styling comes from styles/base.css + styles/app.css
 * (square corners, hairlines, accent colour from the theme). Feature code should
 * compose these rather than inventing new chrome.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { ArrowLeft, ChevronLeft, ChevronRight, Search, X } from 'lucide-react';

/* ------------------------------------------------------------------ Toasts */
type ToastKind = 'success' | 'error' | 'warning' | 'info';
interface Toast { id: number; kind: ToastKind; message: string }
const ToastContext = createContext<{ push: (kind: ToastKind, message: string) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 7000 : 4500);
  }, []);
  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast notice notice-${t.kind === 'success' ? 'ok' : t.kind === 'error' ? 'danger' : t.kind === 'warning' ? 'warn' : 'accent'}`}>
            <span className="grow">{t.message}</span>
            <button className="btn-icon btn-ghost" aria-label="Dismiss" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}><X size={14} /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Replacement for Django `messages`: toast.success('Saved'), toast.error(...). */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast outside ToastProvider');
  return useMemo(() => ({
    success: (m: string) => ctx.push('success', m),
    error: (m: string) => ctx.push('error', m),
    warning: (m: string) => ctx.push('warning', m),
    info: (m: string) => ctx.push('info', m),
  }), [ctx]);
}

/* ------------------------------------------------------------------ Modal */
export function Modal({ open, onClose, title, children, footer, size }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; size?: 'lg' | 'xl';
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${size === 'lg' ? 'modal-lg' : size === 'xl' ? 'modal-xl' : ''}`} role="dialog" aria-modal="true">
        <div className="modal-head between">
          <h2>{title}</h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

/** Imperative confirm dialog: `if (await confirm({title, message})) ...` */
const ConfirmContext = createContext<((o: ConfirmOptions) => Promise<boolean>) | null>(null);
interface ConfirmOptions { title?: string; message: ReactNode; confirmLabel?: string; danger?: boolean }

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<(ConfirmOptions & { resolve: (v: boolean) => void }) | null>(null);
  const confirm = useCallback((o: ConfirmOptions) => new Promise<boolean>((resolve) => setState({ ...o, resolve })), []);
  const close = (v: boolean) => { state?.resolve(v); setState(null); };
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal open={!!state} onClose={() => close(false)} title={state?.title || 'Please confirm'}
        footer={<>
          <button className="btn btn-secondary" onClick={() => close(false)}>Cancel</button>
          <button className={`btn ${state?.danger ? 'btn-danger' : 'btn-primary'}`} onClick={() => close(true)}>{state?.confirmLabel || 'Confirm'}</button>
        </>}>
        <div>{state?.message}</div>
      </Modal>
    </ConfirmContext.Provider>
  );
}
export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('useConfirm outside ConfirmProvider');
  return ctx;
}

/* ------------------------------------------------------------------ Page furniture */
export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <header className="page-header">
      <div className="grow">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p className="muted page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </header>
  );
}

export function Panel({ title, actions, children, footer, flush }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; footer?: ReactNode; flush?: boolean }) {
  return (
    <section className="panel">
      {(title || actions) && <div className="panel-head"><h2>{title}</h2>{actions && <div className="row">{actions}</div>}</div>}
      <div className={flush ? '' : 'panel-body'}>{children}</div>
      {footer && <div className="panel-foot">{footer}</div>}
    </section>
  );
}

export function Stat({ value, label, note }: { value: ReactNode; label: ReactNode; note?: ReactNode }) {
  return <div className="stat"><div className="stat-value">{value}</div><div className="stat-label">{label}</div>{note && <div className="stat-note">{note}</div>}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return <span className="row-tight muted"><span className="spinner" />{label && <span className="small">{label}</span>}</span>;
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="empty"><Spinner label={label} /></div>;
}

export function Empty({ title, children, action }: { title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return <div className="empty"><h3>{title}</h3>{children && <p>{children}</p>}{action && <div style={{ marginTop: 14 }}>{action}</div>}</div>;
}

export function ErrorNotice({ error, title = 'Could not load this page' }: { error: unknown; title?: string }) {
  const msg = (error as any)?.response?.data?.detail || (error as any)?.message || String(error);
  return <div className="notice notice-danger"><div className="notice-title">{title}</div>{typeof msg === 'string' ? msg : JSON.stringify(msg)}</div>;
}

export function Badge({ tone, children }: { tone?: 'accent' | 'ok' | 'warn' | 'danger'; children: ReactNode }) {
  return <span className={`badge ${tone ? `badge-${tone}` : ''}`}>{children}</span>;
}

/* ------------------------------------------------------------------ Forms */
export function Field({ label, required, help, error, children }: { label?: ReactNode; required?: boolean; help?: ReactNode; error?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      {label && <span className="field-label">{label}{required && <span className="req">*</span>}</span>}
      {children}
      {help && !error && <span className="field-help">{help}</span>}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}

export function SearchInput({ value, onChange, placeholder = 'Search…' }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div className="search-input">
      <Search size={14} />
      <input className="input" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

export interface Option { value: string | number; label: string; hint?: string }

/** Searchable select (replaces select2). Single or multiple. Options may be loaded remotely via onSearch. */
export function SearchSelect({ options, value, onChange, multiple, placeholder = 'Select…', onSearch, disabled }: {
  options: Option[]; value: (string | number) | (string | number)[] | null; onChange: (v: any) => void;
  multiple?: boolean; placeholder?: string; onSearch?: (q: string) => void; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const selected = multiple ? ((value as any[]) || []) : value === null || value === undefined || value === '' ? [] : [value];
  const filtered = onSearch ? options : options.filter((o) => `${o.label} ${o.hint || ''}`.toLowerCase().includes(q.toLowerCase()));
  const labelOf = (v: string | number) => options.find((o) => String(o.value) === String(v))?.label ?? String(v);
  const pick = (v: string | number) => {
    if (multiple) {
      const exists = selected.some((s) => String(s) === String(v));
      onChange(exists ? selected.filter((s) => String(s) !== String(v)) : [...selected, v]);
    } else { onChange(v); setOpen(false); }
  };
  return (
    <div className="ss" ref={ref}>
      <button type="button" className="input ss-control" disabled={disabled} onClick={() => setOpen((o) => !o)}>
        {selected.length === 0 && <span className="faint">{placeholder}</span>}
        {!multiple && selected.length === 1 && <span className="truncate">{labelOf(selected[0])}</span>}
        {multiple && selected.map((s) => (
          <span key={String(s)} className="badge ss-chip" onClick={(e) => { e.stopPropagation(); pick(s); }}>{labelOf(s)} <X size={11} /></span>
        ))}
      </button>
      {open && (
        <div className="pop ss-pop">
          <input autoFocus className="input" placeholder="Type to search…" value={q}
            onChange={(e) => { setQ(e.target.value); onSearch?.(e.target.value); }} />
          <div className="ss-list">
            {filtered.length === 0 && <div className="pop-head">No results</div>}
            {filtered.map((o) => (
              <button type="button" key={String(o.value)} className={`pop-item ${selected.some((s) => String(s) === String(o.value)) ? 'is-selected' : ''}`} onClick={() => pick(o.value)}>
                <span className="grow truncate">{o.label}</span>{o.hint && <span className="tiny faint">{o.hint}</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="filter-tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value} className={`filter-tab ${value === t.value ? 'active' : ''}`} onClick={() => onChange(t.value)}>{t.label}</button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ Tables */
export interface Column<T> {
  key: string;
  header: ReactNode;
  render?: (row: T) => ReactNode;
  /** value used for sorting / searching; defaults to row[key] */
  value?: (row: T) => string | number | null | undefined;
  sortable?: boolean;
  className?: string;
}

/**
 * Client-side table with search, sort and paging (replaces jQuery DataTables).
 * For server-paginated data, pass `pageSize={0}` and render <Pagination> yourself.
 */
export function DataTable<T>({ rows, columns, searchable = true, pageSize = 25, empty = 'No records found.', rowKey, onRowClick, toolbar }: {
  rows: T[]; columns: Column<T>[]; searchable?: boolean; pageSize?: number; empty?: ReactNode;
  rowKey: (row: T) => string | number; onRowClick?: (row: T) => void; toolbar?: ReactNode;
}) {
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [page, setPage] = useState(1);
  const valueOf = (row: T, c: Column<T>) => (c.value ? c.value(row) : (row as any)[c.key]);

  const filtered = useMemo(() => {
    let out = rows;
    if (q.trim()) {
      const needle = q.toLowerCase();
      out = out.filter((r) => columns.some((c) => String(valueOf(r, c) ?? '').toLowerCase().includes(needle)));
    }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col) out = [...out].sort((a, b) => {
        const va = valueOf(a, col) ?? ''; const vb = valueOf(b, col) ?? '';
        return (va > vb ? 1 : va < vb ? -1 : 0) * sort.dir;
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, q, sort, columns]);

  useEffect(() => setPage(1), [q, rows.length]);
  const pages = pageSize ? Math.max(1, Math.ceil(filtered.length / pageSize)) : 1;
  const visible = pageSize ? filtered.slice((page - 1) * pageSize, page * pageSize) : filtered;

  return (
    <div className="dt">
      {(searchable || toolbar) && (
        <div className="dt-toolbar between">
          {searchable ? <SearchInput value={q} onChange={setQ} /> : <span />}
          {toolbar}
        </div>
      )}
      <div className="table-scroll">
        <table className={`tbl ${onRowClick ? 'tbl-clickable' : ''}`}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={c.className}
                  onClick={c.sortable !== false && c.header ? () => setSort((s) => (s?.key === c.key ? { key: c.key, dir: (s.dir * -1) as 1 | -1 } : { key: c.key, dir: 1 })) : undefined}
                  style={{ cursor: c.sortable !== false && c.header ? 'pointer' : undefined }}>
                  {c.header}{sort?.key === c.key ? (sort.dir === 1 ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && <tr><td colSpan={columns.length}><div className="empty small">{empty}</div></td></tr>}
            {visible.map((r) => (
              <tr key={rowKey(r)} onClick={onRowClick ? () => onRowClick(r) : undefined}>
                {columns.map((c) => <td key={c.key} className={c.className}>{c.render ? c.render(r) : String(valueOf(r, c) ?? '')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageSize > 0 && filtered.length > pageSize && (
        <Pagination page={page} pages={pages} total={filtered.length} onChange={setPage} />
      )}
    </div>
  );
}

export function Pagination({ page, pages, total, onChange }: { page: number; pages: number; total?: number; onChange: (p: number) => void }) {
  if (pages <= 1) return null;
  return (
    <div className="pagination between">
      <span className="small muted">Page {page} of {pages}{total !== undefined ? ` · ${total} records` : ''}</span>
      <div className="row-tight">
        <button className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => onChange(page - 1)}><ChevronLeft size={14} /> Previous</button>
        <button className="btn btn-secondary btn-sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next <ChevronRight size={14} /></button>
      </div>
    </div>
  );
}

/** Coloured stage label for document workflow statuses (Draft / Under Review / Approved / Draft Under Revision …). */
export function StageStatus({ label, tone }: { label: string; tone?: 'ok' | 'warn' | 'danger' | 'muted' | 'accent' }) {
  const cls = tone === 'ok' ? 'status-completed' : tone === 'warn' ? 'status-partially_signed' : tone === 'danger' ? 'status-declined' : tone === 'accent' ? 'status-accent' : 'status-draft';
  return <span className={`status ${cls}`}>{label}</span>;
}

/** "← Back to …" link shown above a page header, for pages that belong to a parent record. */
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="back-link"><ArrowLeft size={14} /> {children}</Link>
  );
}
