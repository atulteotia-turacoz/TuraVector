/** Cell renderer (display_for_field) and form widgets for every Django field kind. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, CircleHelp, ExternalLink, Pencil, X } from 'lucide-react';
import { api } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { API, adminPath, type Cell, type FieldMeta } from '@/lib/admin';
import { SearchSelect, type Option } from '@/components/ui';

export function BoolIcon({ value }: { value: boolean | null | undefined }) {
  if (value === null || value === undefined) return <span className="bool-unknown" title="Unknown" aria-label="Unknown"><CircleHelp size={15} /></span>;
  return value
    ? <span className="bool-yes" title="Yes" aria-label="Yes"><Check size={15} /></span>
    : <span className="bool-no" title="No" aria-label="No"><X size={15} /></span>;
}

export function CellView({ cell, changeFileTo }: { cell: Cell | undefined; changeFileTo?: string }) {
  if (!cell) return <span className="faint">-</span>;
  if (cell.kind === 'bool') return <BoolIcon value={cell.bool} />;
  if (cell.kind === 'datetime') return <span className="nowrap">{formatDateTime(cell.value)}</span>;
  if (cell.kind === 'date') return <span className="nowrap">{formatDate(cell.value)}</span>;
  if (cell.kind === 'file') return cell.url ? <a className="act" href={cell.url} target="_blank" rel="noreferrer">{cell.text}</a> : <span>{cell.text}</span>;
  if (cell.kind === 'link') return changeFileTo ? <Link className="btn btn-secondary btn-sm" to={changeFileTo}>{cell.text}</Link> : <span>{cell.text}</span>;
  if (cell.link) return <Link className="act" to={adminPath(cell.link)}>{cell.text}</Link>;
  if (cell.href) return <a className="act" href={cell.href} target="_blank" rel="noreferrer">{cell.text}</a>;
  return <span style={{ whiteSpace: 'pre-wrap' }}>{cell.text}</span>;
}

/* ---------- datetime helpers: API speaks ISO-8601 UTC; inputs speak browser-local time ---------- */
const pad = (n: number) => String(n).padStart(2, '0');
export function isoToLocalInput(v: string | null | undefined): string {
  if (!v) return '';
  const d = new Date(v);
  if (isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
export function localInputToIso(v: string): string | null {
  if (!v) return null;
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d.toISOString();
}

/* ---------- FK / M2M select backed by the autocomplete endpoint ---------- */
export function RelatedSelect({ app, model, field, value, onChange, multiple, disabled, loadAll }: {
  app: string; model: string; field: string; value: any; onChange: (v: any) => void; multiple?: boolean; disabled?: boolean; loadAll?: boolean;
}) {
  const [options, setOptions] = useState<Option[]>([]);
  const [known, setKnown] = useState<Record<string, string>>({});
  const timer = useRef<number>();
  const load = (q: string) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try {
        const { data } = await api.get(`${API}/models/${app}/${model}/autocomplete`, { params: { field, q, all: loadAll || undefined } });
        setOptions(data.results);
        setKnown((k) => ({ ...k, ...Object.fromEntries(data.results.map((o: Option) => [String(o.value), o.label])) }));
      } catch { /* ignore */ }
    }, q ? 220 : 0);
  };
  useEffect(() => { load(''); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [app, model, field]);

  // value is {value,label} | [{value,label}] — SearchSelect wants raw ids plus options containing the labels
  const selected = multiple ? ((value as any[]) || []) : value ? [value] : [];
  const merged = useMemo(() => {
    const map = new Map<string, Option>();
    selected.forEach((s: any) => map.set(String(s.value), { value: s.value, label: s.label ?? known[String(s.value)] ?? String(s.value) }));
    options.forEach((o) => map.set(String(o.value), o));
    return Array.from(map.values());
  }, [options, selected, known]);
  const labelOf = (v: string | number) => merged.find((o) => String(o.value) === String(v))?.label ?? String(v);
  return (
    <SearchSelect
      options={merged}
      multiple={multiple}
      disabled={disabled}
      placeholder={multiple ? 'Choose…' : '---------'}
      onSearch={loadAll ? undefined : load}
      value={multiple ? selected.map((s: any) => s.value) : selected[0]?.value ?? null}
      onChange={(v: any) => {
        if (multiple) onChange((v as any[]).map((x) => ({ value: x, label: labelOf(x) })));
        else onChange(v === null || v === undefined || v === '' ? null : { value: v, label: labelOf(v) });
      }}
    />
  );
}

/* ---------- One editable widget ---------- */
export interface FileState { file?: File | null; clear?: boolean }

export function FieldInput({ meta, value, onChange, app, model, fieldKey, fileState, onFile, invalid }: {
  meta: FieldMeta; value: any; onChange: (v: any) => void; app: string; model: string;
  /** autocomplete field key (`field` or `Inline.Label:field`) */
  fieldKey?: string; fileState?: FileState; onFile?: (s: FileState) => void; invalid?: boolean;
}) {
  const cls = `input ${invalid ? 'error' : ''}`;
  const id = `f-${fieldKey || meta.name}`;
  switch (meta.kind) {
    case 'text':
      return <textarea id={id} className={cls} rows={meta.name === 'message_content' || meta.name === 'content' ? 8 : 4} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />;
    case 'json':
      return <textarea id={id} className={`${cls} json-input`} rows={6} spellCheck={false} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />;
    case 'bool':
      return <label className="check" style={{ paddingTop: 7 }}><input id={id} type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} /><span className="sr-only visually-hidden">{meta.label}</span></label>;
    case 'nullbool':
      return (
        <select id={id} className={cls} style={{ maxWidth: 200 }} value={value === null || value === undefined ? 'unknown' : value ? 'true' : 'false'}
          onChange={(e) => onChange(e.target.value === 'unknown' ? null : e.target.value === 'true')}>
          <option value="unknown">Unknown</option><option value="true">Yes</option><option value="false">No</option>
        </select>
      );
    case 'choice':
      return (
        <select id={id} className={cls} style={{ maxWidth: 420 }} value={value === null || value === undefined ? '' : String(value)}
          onChange={(e) => {
            const raw = e.target.value;
            const match = meta.choices?.find(([v]) => String(v) === raw);
            onChange(raw === '' ? null : match ? match[0] : raw);
          }}>
          {(!meta.required || value === null || value === undefined || value === '') && <option value="">---------</option>}
          {meta.choices?.map(([v, l]) => <option key={String(v)} value={String(v)}>{l}</option>)}
        </select>
      );
    case 'int': case 'float': case 'decimal':
      return <input id={id} className={cls} style={{ maxWidth: 220 }} type="number" step={meta.kind === 'int' ? 1 : 'any'} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />;
    case 'date':
      return <input id={id} className={cls} style={{ maxWidth: 220 }} type="date" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} />;
    case 'datetime':
      return (
        <div className="row wrap">
          <input id={id} className={cls} style={{ maxWidth: 260 }} type="datetime-local" step={1} value={isoToLocalInput(value)} onChange={(e) => onChange(localInputToIso(e.target.value))} />
          <button type="button" className="act" onClick={() => onChange(new Date().toISOString())}>Now</button>
          {!meta.required && value && <button type="button" className="act" onClick={() => onChange(null)}>Clear</button>}
        </div>
      );
    case 'fk':
      return (
        <div className="fk-row">
          <RelatedSelect app={app} model={model} field={fieldKey || meta.name} value={value} onChange={onChange} />
          {value && meta.rel?.registered && meta.rel.app && (
            <Link className="btn btn-ghost btn-icon" title={`Change selected ${meta.rel.verbose_name}`} aria-label={`Change selected ${meta.rel.verbose_name}`}
              to={adminPath({ app: meta.rel.app, model: meta.rel.model!, pk: String(value.value) })}><Pencil size={14} /></Link>
          )}
        </div>
      );
    case 'm2m':
      return (
        <div className="m2m-box">
          <RelatedSelect app={app} model={model} field={fieldKey || meta.name} value={value || []} onChange={onChange} multiple loadAll />
          <span className="field-help">{(value || []).length} selected. Click a chip to remove it.</span>
        </div>
      );
    case 'file': case 'image': {
      const cur = value as { name: string; url: string | null } | null;
      return (
        <div>
          {cur && (
            <div className="file-current">
              <span className="muted">Currently:</span>
              {cur.url ? <a className="act" href={cur.url} target="_blank" rel="noreferrer">{cur.name} <ExternalLink size={11} style={{ display: 'inline' }} /></a> : <span>{cur.name}</span>}
              {!meta.required && (
                <label className="check"><input type="checkbox" checked={!!fileState?.clear} onChange={(e) => onFile?.({ ...fileState, clear: e.target.checked })} /> Clear</label>
              )}
            </div>
          )}
          <div className="row-tight">
            {cur && <span className="muted small">Change:</span>}
            <input id={id} type="file" accept={meta.allowed_extensions?.map((x) => `.${x}`).join(',') || (meta.kind === 'image' ? 'image/*' : undefined)}
              onChange={(e) => onFile?.({ ...fileState, file: e.target.files?.[0] ?? null })} />
          </div>
        </div>
      );
    }
    case 'email':
      return <input id={id} className={cls} style={{ maxWidth: 420 }} type="email" value={value ?? ''} maxLength={meta.max_length ?? undefined} onChange={(e) => onChange(e.target.value)} />;
    case 'url':
      return <input id={id} className={cls} type="url" value={value ?? ''} maxLength={meta.max_length ?? undefined} onChange={(e) => onChange(e.target.value)} />;
    case 'password':
      return <input id={id} className={cls} style={{ maxWidth: 360 }} type="password" autoComplete="new-password" value={value ?? ''} onChange={(e) => onChange(e.target.value)} />;
    case 'usable_password':
      return (
        <div className="row wrap" style={{ paddingTop: 6 }}>
          {(meta.choices || []).map(([v, l]) => (
            <label key={String(v)} className="check"><input type="radio" name={id} checked={String(value ?? 'true') === String(v)} onChange={() => onChange(String(v))} /> {l}</label>
          ))}
        </div>
      );
    default:
      return <input id={id} className={cls} style={meta.max_length && meta.max_length <= 60 ? { maxWidth: 420 } : undefined} type="text" value={value ?? ''} maxLength={meta.max_length ?? undefined} onChange={(e) => onChange(e.target.value)} />;
  }
}
