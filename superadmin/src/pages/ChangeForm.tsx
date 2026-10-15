import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, History, Plus, Trash2 } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { API, formErrors, useModelConfig, type Cell, type FieldMeta, type FormErrorPayload, type InlineMeta } from '@/lib/admin';
import { ErrorNotice, Loading, PageHeader, Panel, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';
import { CellView, FieldInput, type FileState } from '@/components/fields';

function capfirst(s: string) { return s ? s[0].toUpperCase() + s.slice(1) : s; }

interface ObjectData {
  pk: string; str: string; values: Record<string, any>; display: Record<string, any>;
  inlines: { label: string; rows: { pk: string; str: string; values: Record<string, any>; display: Record<string, Cell> }[] }[];
}
interface InlineRow { pk?: string; values: Record<string, any>; display?: Record<string, Cell>; DELETE?: boolean }

function ErrorList({ errors }: { errors?: string[] }) {
  if (!errors?.length) return null;
  return <ul className="errorlist" role="alert">{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>;
}

function PasswordHash({ display, pk }: { display: any; pk?: string }) {
  return (
    <div className="readonly">
      {display?.usable === false ? <span>No password set.</span> : (
        <div className="pw-items">{(display?.items || []).map(([k, v]: [string, string]) => <span key={k}><strong>{k}:</strong>{v}</span>)}</div>
      )}
      {pk && <div className="field-help">Raw passwords are not stored, so there is no way to see the user’s password, but you can change or unset the password using <Link className="act" to={`/authentication/user/${pk}/password/`}>this form</Link>.</div>}
    </div>
  );
}

function InlineTable({ meta, rows, setRows, app, model, errors, readOnly }: {
  meta: InlineMeta; rows: InlineRow[]; setRows: (r: InlineRow[]) => void; app: string; model: string;
  errors?: Record<string, Record<string, string[]>>; readOnly: boolean;
}) {
  const update = (i: number, patch: Partial<InlineRow>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <section className="panel fieldset">
      <div className="fieldset-head"><h2>{capfirst(meta.verbose_name_plural)}</h2></div>
      <ErrorList errors={errors?.__formset__?.__all__} />
      <div className="table-scroll">
        <table className="tbl inline-table">
          <thead>
            <tr>
              {meta.fields.map((f) => <th key={f.name}>{f.label}{f.required && !f.readonly && <span className="req" style={{ color: 'var(--danger)' }}> *</span>}</th>)}
              {!readOnly && <th style={{ width: 70 }}>Delete?</th>}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={meta.fields.length + 1} className="muted small">No {meta.verbose_name_plural}.</td></tr>}
            {rows.map((r, i) => {
              const errs = errors?.[String(i)];
              return (
                <tr key={r.pk ?? `new-${i}`} className={r.DELETE ? 'deleted' : ''}>
                  {meta.fields.map((f) => (
                    <td key={f.name}>
                      <ErrorList errors={errs?.[f.name]} />
                      {f.readonly || readOnly
                        ? <div className="readonly">{r.display?.[f.name] ? <CellView cell={r.display[f.name]} /> : <span className="faint">-</span>}</div>
                        : <FieldInput meta={f} value={r.values[f.name]} app={app} model={model} fieldKey={`${meta.label}:${f.name}`}
                            onChange={(v) => update(i, { values: { ...r.values, [f.name]: v } })} invalid={!!errs?.[f.name]} />}
                    </td>
                  ))}
                  {!readOnly && (
                    <td>
                      {r.pk
                        ? <label className="check"><input type="checkbox" checked={!!r.DELETE} onChange={(e) => update(i, { DELETE: e.target.checked })} aria-label="Delete" /></label>
                        : <button type="button" className="btn btn-ghost btn-icon" aria-label="Remove row" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={14} /></button>}
                      <ErrorList errors={errs?.__all__} />
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!readOnly && (
        <div className="panel-foot">
          <button type="button" className="act act-accent row-tight" onClick={() => setRows([...rows, { values: {} }])}><Plus size={12} /> Add another {meta.verbose_name}</button>
        </div>
      )}
    </section>
  );
}

export default function ChangeForm() {
  const { app = '', model = '', pk } = useParams();
  const isAdd = !pk;
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const cfg = useModelConfig(app, model);
  const obj = useQuery({
    queryKey: ['admin', 'obj', app, model, pk ?? '__add__'],
    queryFn: async () => (isAdd
      ? { pk: '', str: '', display: {}, inlines: [], ...(await api.get(`${API}/models/${app}/${model}/add`)).data }
      : (await api.get<ObjectData>(`${API}/models/${app}/${model}/${encodeURIComponent(pk!)}`)).data) as ObjectData,
    staleTime: 0,
    gcTime: 0,
  });
  const [values, setValues] = useState<Record<string, any>>({});
  const [files, setFiles] = useState<Record<string, FileState>>({});
  const [inlines, setInlines] = useState<Record<string, InlineRow[]>>({});
  const [errors, setErrors] = useState<FormErrorPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [formKey, setFormKey] = useState(0);

  useEffect(() => {
    if (!obj.data || !cfg.data) return;
    setValues(obj.data.values || {});
    setFiles({});
    setErrors(null);
    const layout = isAdd ? cfg.data.add_form : cfg.data.change_form;
    const next: Record<string, InlineRow[]> = {};
    layout.inlines.forEach((inl) => {
      const existing = obj.data!.inlines.find((x) => x.label === inl.label)?.rows ?? [];
      next[inl.label] = [
        ...existing.map((r) => ({ pk: r.pk, values: r.values, display: r.display })),
        ...Array.from({ length: inl.extra }, () => ({ values: {} })),
      ];
    });
    setInlines(next);
  }, [obj.data, cfg.data, isAdd, formKey]);

  const layout = cfg.data ? (isAdd ? cfg.data.add_form : cfg.data.change_form) : null;
  const viewOnly = !!layout?.view_only;

  const fileFields = useMemo(() => Object.values(layout?.fields ?? {}).filter((f) => f.kind === 'file' || f.kind === 'image').map((f) => f.name), [layout]);

  if (cfg.isLoading || obj.isLoading) return <Loading />;
  if (cfg.error) return <ErrorNotice error={cfg.error} />;
  if (obj.error) return <ErrorNotice error={obj.error} title="Could not load this object" />;
  const c = cfg.data!;
  const data = obj.data!;

  const submit = async (then: 'save' | 'continue' | 'addanother') => {
    setBusy(true);
    setErrors(null);
    const payload = {
      data: values, then,
      clear: fileFields.filter((f) => files[f]?.clear),
      inlines: Object.fromEntries(Object.entries(inlines).map(([label, rows]) => [label, rows.map((r) => ({ pk: r.pk, values: r.values, DELETE: r.DELETE }))])),
    };
    const fd = new FormData();
    fd.append('payload', JSON.stringify(payload));
    fileFields.forEach((f) => { const file = files[f]?.file; if (file) fd.append(`file__${f}`, file); });
    try {
      const url = isAdd ? `${API}/models/${app}/${model}/add` : `${API}/models/${app}/${model}/${encodeURIComponent(pk!)}`;
      const { data: res } = await api.post(url, fd);
      toast.success(res.message);
      void qc.invalidateQueries({ queryKey: ['admin'] });
      if (isAdd && c.label === 'authentication.User' && then !== 'addanother') {
        navigate(`/${app}/${model}/${res.pk}/change/`);  // UserAdmin.response_add always continues editing
      } else if (then === 'continue') {
        if (isAdd) navigate(`/${app}/${model}/${encodeURIComponent(res.pk)}/change/`);
        else { await obj.refetch(); setFormKey((k) => k + 1); }
      } else if (then === 'addanother') {
        if (isAdd) { await obj.refetch(); setFormKey((k) => k + 1); } else navigate(`/${app}/${model}/add/`);
      } else {
        navigate(`/${app}/${model}/`);
      }
    } catch (err) {
      const fe = formErrors(err);
      if (fe && (fe.errors || fe.non_field_errors || fe.inline_errors)) setErrors(fe);
      else toast.error(errorMessage(err));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setBusy(false);
    }
  };
  const onSubmit = (e: FormEvent) => { e.preventDefault(); void submit('save'); };

  const renderField = (name: string): ReactNode => {
    const meta: FieldMeta | undefined = layout!.fields[name];
    if (!meta) return null;
    // UserCreationForm: password inputs are hidden when password-based authentication is disabled
    if ((meta.kind === 'password') && String(values.usable_password ?? 'true') === 'false') return null;
    const err = errors?.errors?.[name];
    let body: ReactNode;
    if (meta.kind === 'password_hash') body = <PasswordHash display={data.display[name]} pk={isAdd ? undefined : data.pk} />;
    else if (meta.readonly || meta.kind === 'computed') {
      const cell = data.display[name] as Cell | undefined;
      body = <div className="readonly">{cell ? <CellView cell={cell} /> : <span className="faint">-</span>}</div>;
    } else {
      body = (
        <FieldInput meta={meta} value={values[name]} app={app} model={model} invalid={!!err}
          onChange={(v) => setValues((s) => ({ ...s, [name]: v }))}
          fileState={files[name]} onFile={(st) => setFiles((s) => ({ ...s, [name]: st }))} />
      );
    }
    const labelReq = meta.required && !meta.readonly && meta.kind !== 'computed' && meta.kind !== 'password_hash';
    return (
      <div key={name} className={`form-row ${err ? 'has-error' : ''}`}>
        <label className={`form-label ${labelReq ? 'required' : ''}`} htmlFor={`f-${name}`}>{meta.label}{labelReq && <span style={{ color: 'var(--danger)' }}> *</span>}</label>
        <div style={{ minWidth: 0 }}>
          <ErrorList errors={err} />
          {body}
          {meta.help_text && meta.kind !== 'password_hash' && <span className="field-help">{meta.help_text}</span>}
        </div>
      </div>
    );
  };

  const verb = isAdd ? 'Add' : viewOnly ? 'View' : 'Change';
  const changeFile = c.extra_links.find((l) => l.route === 'change_file');
  const nErr = (errors?.errors ? Object.keys(errors.errors).length : 0) + (errors?.non_field_errors?.length ?? 0) + (errors?.inline_errors ? 1 : 0);

  return (
    <>
      <Crumbs items={[
        { label: c.app_name, to: `/${app}/` },
        { label: capfirst(c.verbose_name_plural), to: `/${app}/${model}/` },
        { label: isAdd ? `Add ${c.verbose_name}` : data.str },
      ]} />
      <PageHeader title={`${verb} ${c.verbose_name}`} subtitle={!isAdd ? data.str : undefined}
        actions={!isAdd && (<>
          {app === 'documents' && model === 'document' && (
            <Link className="btn btn-secondary btn-sm" to={`/documents/document/${encodeURIComponent(pk!)}/update-status/`}>Update Status</Link>
          )}
          {app === 'documents' && model === 'documentversion' && (
            <Link className="btn btn-secondary btn-sm" to={`/documents/version/${encodeURIComponent(pk!)}/update-status/`}>Update Status</Link>
          )}
          <Link className="btn btn-secondary btn-sm" to={`/${app}/${model}/${encodeURIComponent(pk!)}/history/`}><History size={14} /> History</Link>
        </>)} />
      {c.label === 'authentication.User' && isAdd && (
        <p className="muted" style={{ marginBottom: 14 }}>First, enter a username and password. Then, you’ll be able to edit more user options.</p>
      )}
      {errors && (
        <div className="notice notice-danger" role="alert" style={{ marginBottom: 16 }}>
          {nErr === 1 ? 'Please correct the error below.' : 'Please correct the errors below.'}
          <ErrorList errors={errors.non_field_errors} />
        </div>
      )}
      <form onSubmit={onSubmit} noValidate key={formKey}>
        {layout!.fieldsets.map((fs, i) => {
          const collapse = fs.classes.includes('collapse');
          const body = <div>{fs.description && <p className="field-help" style={{ padding: '10px 18px 0' }}>{fs.description}</p>}{fs.fields.map(renderField)}</div>;
          const hasErr = fs.fields.some((f) => errors?.errors?.[f]);
          if (collapse) {
            return (
              <details key={i} className="panel fieldset" open={hasErr || undefined}>
                <summary className="fieldset-head"><ChevronDown size={14} /><h2>{fs.name || 'Details'}</h2><span className="tiny faint">(show)</span></summary>
                {body}
              </details>
            );
          }
          return (
            <section key={i} className="panel fieldset">
              {fs.name && <div className="fieldset-head"><h2>{fs.name}</h2></div>}
              {body}
            </section>
          );
        })}
        {layout!.inlines.map((inl) => (
          <div key={inl.label} style={{ marginTop: 18 }}>
            <InlineTable meta={inl} rows={inlines[inl.label] ?? []} setRows={(r) => setInlines((s) => ({ ...s, [inl.label]: r }))}
              app={app} model={model} errors={errors?.inline_errors?.[inl.label]} readOnly={viewOnly} />
          </div>
        ))}
        <div className="submit-row">
          {viewOnly ? (
            <Link className="btn btn-secondary" to={`/${app}/${model}/`}>Close</Link>
          ) : (
            <>
              <button className="btn btn-primary" disabled={busy}>Save</button>
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => submit('addanother')}>Save and add another</button>
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => submit('continue')}>Save and continue editing</button>
            </>
          )}
          {!isAdd && changeFile && (
            <Link className="btn btn-secondary" to={`/${app}/${model}/${encodeURIComponent(pk!)}/change-file/`}>{changeFile.label}</Link>
          )}
          {!isAdd && c.perms.delete && (
            <Link className="btn btn-ghost push" style={{ color: 'var(--danger)' }} to={`/${app}/${model}/${encodeURIComponent(pk!)}/delete/`}><Trash2 size={14} /> Delete</Link>
          )}
        </div>
      </form>
      {!isAdd && !viewOnly && Object.keys(layout!.fields).length === 0 && <Panel><p className="muted">No editable fields.</p></Panel>}
    </>
  );
}
