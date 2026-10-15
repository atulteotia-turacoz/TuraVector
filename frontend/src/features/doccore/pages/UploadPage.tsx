/** upload_document_with_owner_view — documents/upload_with_owner.html (/documents/upload/ and /documents/main-document/). */
import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, CloudUpload, FileText, PenLine, ReceiptText, ShieldCheck, Upload, X } from 'lucide-react';
import { api, toFormData } from '@/lib/api';
import { ErrorNotice, Field, Loading, PageHeader, SearchSelect, Spinner, type Option } from '@/components/ui';
import { RichTextEditor, htmlIsEmpty } from '@/components/RichTextEditor';
import { ACCEPT_DOCUMENTS, ALLOWED_EXTENSIONS, filesizeformat, useDocPage, useSubmitHandlers } from '../shared';

interface Choice { value: number; label: string }
interface RateCardService {
  service_id: number; name: string; description: string; unit: string; unit_label: string; rate: number;
  tax_percent: number; currency: string;
}
interface Options {
  is_admin: boolean; page_title: string;
  document_types: Choice[]; countries: Choice[]; brands: Choice[]; therapeutic_areas: Choice[];
  rate_card: RateCardService[];
}

const COUNTED_UNITS = ['per_page', 'per_word', 'per_hour', 'per_document'];
const inr = (v: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(v);

/** Remote user search (search_users_api, Select2 format). */
export function useOwnerSearch(enabled: boolean) {
  const [options, setOptions] = useState<Option[]>([]);
  const known = useRef<Map<string, Option>>(new Map());
  const timer = useRef<number>();
  const search = useCallback((term: string) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try {
        const { data } = await api.get('/api/doccore/search-users', { params: { q: term || '', page: 1 } });
        const opts: Option[] = data.results.map((u: any) => ({ value: u.id, label: u.text, hint: u.email }));
        opts.forEach((o) => known.current.set(String(o.value), o));
        setOptions(opts);
      } catch { setOptions([]); }
    }, 300);
  }, []);
  useEffect(() => { if (enabled) search(''); }, [enabled, search]);
  const withSelected = (selected: string | number | null) => {
    if (selected === null || selected === '') return options;
    const sel = known.current.get(String(selected));
    return sel && !options.some((o) => String(o.value) === String(selected)) ? [sel, ...options] : options;
  };
  return { search, withSelected };
}

export default function UploadPage() {
  const q = useDocPage<Options>(['upload-options'], '/api/doccore/upload/options');
  const { onSuccess, onError } = useSubmitHandlers();
  const [owner, setOwner] = useState<string | number | null>(null);
  const [values, setValues] = useState({ document_name: '', document_type: '', country: '', brand: '', therapeutic_area: '' });
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<'file' | 'text'>('file');
  const [text, setText] = useState('');
  const [picked, setPicked] = useState<number[]>([]);
  const [qty, setQty] = useState<Record<number, string>>({});
  const [requirement, setRequirement] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const ownerSearch = useOwnerSearch(!!q.data?.is_admin);

  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const o = q.data!;

  const set = (k: keyof typeof values, v: string) => setValues((s) => ({ ...s, [k]: v }));

  const pick = (f: File | null | undefined) => {
    if (!f) { setFile(null); return; }
    const ext = (f.name.split('.').pop() || '').toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      window.alert(`Invalid file type. Please select a file with one of these extensions: ${ALLOWED_EXTENSIONS.join(', ')}`);
      setFile(null); if (inputRef.current) inputRef.current.value = '';
      return;
    }
    if (f.size > 50 * 1024 * 1024) {
      window.alert('File size is too large. Maximum allowed size is 50MB.');
      setFile(null); if (inputRef.current) inputRef.current.value = '';
      return;
    }
    setFile(f);
    // Auto-fill document name from filename
    if (!values.document_name) {
      const base = f.name.lastIndexOf('.') > 0 ? f.name.substring(0, f.name.lastIndexOf('.')) : f.name;
      set('document_name', base);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) pick(f);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (mode === 'file' && !file) { window.alert('Please select a file to upload.'); return; }
    if (mode === 'text' && htmlIsEmpty(text)) { window.alert('Please write your text first.'); return; }
    setSubmitting(true); setErrors({});
    try {
      const services = picked.map((id) => ({ service_id: id, quantity: qty[id] || 1 }));
      const { data } = await api.post('/api/doccore/upload', toFormData({
        ...values, document_owner: owner ?? '',
        // the text travels as a file: with pictures it can be bigger than a form field allows
        ...(mode === 'file' ? { document_file: file } : { content_file: new Blob([text], { type: 'text/html' }) }),
        ...(services.length ? { services: JSON.stringify(services), requirement } : {}),
      }));
      onSuccess(data);
    } catch (err) {
      onError(err, setErrors);
      setSubmitting(false);
    }
  };

  const select = (k: 'document_type' | 'country' | 'brand' | 'therapeutic_area', list: Choice[], placeholder: string) => (
    <select className="input" value={values[k]} onChange={(e) => set(k, e.target.value)}>
      <option value="">{placeholder}</option>
      {list.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
    </select>
  );
  const labelOf = (list: Choice[], v: string) => list.find((c) => String(c.value) === v)?.label;
  const ownerLabel = owner !== null && owner !== '' ? ownerSearch.withSelected(owner).find((x) => String(x.value) === String(owner))?.label : null;
  const ext = file ? (file.name.split('.').pop() || '').toUpperCase() : '';
  const card = o.rate_card ?? [];
  const chosen = card.filter((s) => picked.includes(s.service_id));
  const lineAmount = (s: RateCardService) => s.rate * (Number(qty[s.service_id]) || 1);
  const subtotal = chosen.reduce((t, s) => t + lineAmount(s), 0);
  const gst = chosen.reduce((t, s) => t + (lineAmount(s) * s.tax_percent) / 100, 0);
  const checklist = [
    mode === 'file' ? { label: 'File selected', done: !!file } : { label: 'Text written', done: !htmlIsEmpty(text) },
    { label: 'Document name', done: !!values.document_name.trim() },
    { label: 'Document type', done: !!values.document_type },
    { label: 'Country', done: !!values.country },
  ];
  const ready = checklist.every((c) => c.done);

  return (
    <div className="up">
      <PageHeader title={o.page_title} subtitle="Add a new document. You can upload more versions of it later." />

      <form onSubmit={submit} className="up-grid">
        <div className="stack-lg">
          {/* 1 · File */}
          <section className="panel">
            <div className="panel-head">
              <h2 className="up-step"><span>1</span> {mode === 'file' ? 'Choose the file' : 'Write your text'}</h2>
              <div className="up-mode" role="group" aria-label="How to add the document">
                <button type="button" className={mode === 'file' ? 'is-on' : ''} aria-pressed={mode === 'file'} onClick={() => setMode('file')}><FileText size={13} /> Upload a file</button>
                <button type="button" className={mode === 'text' ? 'is-on' : ''} aria-pressed={mode === 'text'} onClick={() => setMode('text')}><PenLine size={13} /> Write text</button>
              </div>
            </div>
            {mode === 'text' ? (
              <div className="panel-body">
                <RichTextEditor value={text} onChange={setText} placeholder="Write or paste your requirement, abstract or manuscript text here…" />
                {errors.content_html && <span className="field-error">{errors.content_html}</span>}
              </div>
            ) : (
            <div className="panel-body">
              <input ref={inputRef} type="file" className="visually-hidden" accept={ACCEPT_DOCUMENTS} onChange={(e) => pick(e.target.files?.[0])} />
              {file ? (
                <div className="up-file">
                  <span className="vr-ext">{ext}</span>
                  <span className="grow" style={{ minWidth: 0 }}>
                    <span className="vr-title" title={file.name}>{file.name}</span>
                    <span className="vr-sub">{filesizeformat(file.size)} · ready to upload</span>
                  </span>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => inputRef.current?.click()}>Replace</button>
                  <button type="button" className="btn btn-ghost btn-sm" aria-label="Remove file" onClick={() => { setFile(null); if (inputRef.current) inputRef.current.value = ''; }}><X size={14} /></button>
                </div>
              ) : (
                <div className={`dropzone up-drop ${over ? 'is-over' : ''}`} role="button" tabIndex={0}
                  onClick={() => inputRef.current?.click()}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setOver(true); }}
                  onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); setOver(false); }}
                  onDrop={onDrop}>
                  <CloudUpload size={30} className="dc-accent" />
                  <div className="up-drop-title">Drag and drop your file here, or <span className="act act-accent">browse</span></div>
                  <div className="small muted">PDF, DOC, DOCX, XLS, XLSX, PPT or PPTX · up to 50 MB</div>
                </div>
              )}
              {errors.document_file && <span className="field-error">{errors.document_file}</span>}
              <p className="field-help" style={{ marginTop: 10 }}>The document name is filled in from the file name — you can change it below.</p>
            </div>
            )}
          </section>

          {/* 2 · Details */}
          <section className="panel">
            <div className="panel-head"><h2 className="up-step"><span>2</span> Document details</h2></div>
            <div className="panel-body">
              <div className="form-grid">
                <div className="span-2">
                  <Field label="Document Name" required error={errors.document_name}>
                    <input className="input" placeholder="Enter document name" value={values.document_name}
                      maxLength={500} onChange={(e) => set('document_name', e.target.value)} />
                  </Field>
                </div>
                <Field label="Document Type" required error={errors.document_type}>{select('document_type', o.document_types, 'Select a type')}</Field>
                <Field label="Country" required error={errors.country}>{select('country', o.countries, 'Select a country')}</Field>
                <Field label="Brand" help="Optional" error={errors.brand}>{select('brand', o.brands, 'No brand')}</Field>
                <Field label="Therapeutic Area" help="Optional" error={errors.therapeutic_area}>{select('therapeutic_area', o.therapeutic_areas, 'None')}</Field>
              </div>
            </div>
          </section>

          {/* Services from the workspace's rate card */}
          {card.length > 0 && (
            <section className="panel">
              <div className="panel-head"><h2 className="up-step"><span>3</span> Services required</h2><span className="small muted">Optional</span></div>
              <div className="panel-body">
                <Field label="Choose the services you need" error={errors.services}
                  help="From your institution's rate card. Turacoz checks the request and sends the invoice to your administrator.">
                  <SearchSelect multiple value={picked} placeholder="Select one or more services…"
                    options={card.map((s) => ({ value: s.service_id, label: s.name, hint: `${inr(s.rate)}${s.unit_label ? ` · ${s.unit_label.toLowerCase()}` : ''}` }))}
                    onChange={(v: (string | number)[]) => setPicked(v.map(Number))} />
                </Field>
                {chosen.length > 0 && <>
                  <table className="up-svc">
                    <thead><tr><th>Service</th><th className="num">Rate</th><th className="num">Quantity</th><th className="num">Amount</th><th /></tr></thead>
                    <tbody>
                      {chosen.map((s) => (
                        <tr key={s.service_id}>
                          <td><strong>{s.name}</strong>{s.description && <div className="tiny faint">{s.description}</div>}</td>
                          <td className="num small">{inr(s.rate)}{s.unit_label && <div className="tiny faint">{s.unit_label.toLowerCase()}</div>}</td>
                          <td className="num">{COUNTED_UNITS.includes(s.unit)
                            ? <input className="input" type="number" min="1" step="1" aria-label={`Quantity for ${s.name}`}
                                placeholder={s.unit === 'per_word' ? 'Words' : s.unit === 'per_page' ? 'Pages' : s.unit === 'per_hour' ? 'Hours' : '1'}
                                value={qty[s.service_id] ?? ''} onChange={(e) => setQty((q2) => ({ ...q2, [s.service_id]: e.target.value }))} />
                            : <span className="small muted">1</span>}</td>
                          <td className="num">{inr(lineAmount(s))}</td>
                          <td><button type="button" className="btn btn-ghost btn-icon" aria-label={`Remove ${s.name}`} onClick={() => setPicked((p2) => p2.filter((x) => x !== s.service_id))}><X size={14} /></button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div style={{ marginTop: 14 }}>
                    <Field label="Requirement / instructions" help="Anything Turacoz should know: deadline, target journal, word limit…">
                      <textarea className="input" rows={3} value={requirement} onChange={(e) => setRequirement(e.target.value)} />
                    </Field>
                  </div>
                </>}
              </div>
            </section>
          )}

          {/* Owner (admins only) */}
          {o.is_admin && (
            <section className="panel">
              <div className="panel-head">
                <h2 className="up-step"><span>{card.length ? 4 : 3}</span> Document owner</h2>
                <span className="badge badge-accent row-tight"><ShieldCheck size={12} /> Admin</span>
              </div>
              <div className="panel-body">
                <Field label="Upload on behalf of" error={errors.document_owner}
                  help="Search and select who will own this document. If nobody is selected, you will be the owner.">
                  <div className="row-tight">
                    <div className="grow">
                      <SearchSelect options={ownerSearch.withSelected(owner)} value={owner} onChange={setOwner}
                        placeholder="Search users by name or email..." onSearch={ownerSearch.search} />
                    </div>
                    {owner !== null && owner !== '' && (
                      <button type="button" className="btn btn-ghost btn-icon" aria-label="Clear owner" onClick={() => setOwner(null)}><X size={14} /></button>
                    )}
                  </div>
                </Field>
              </div>
            </section>
          )}
        </div>

        {/* Summary + submit */}
        <aside className="panel up-summary">
          <div className="panel-head"><h2>Upload summary</h2></div>
          <div className="panel-body">
            <dl className="up-kv">
              {mode === 'file'
                ? <><dt>File</dt><dd>{file ? file.name : <span className="faint">Not chosen</span>}</dd></>
                : <><dt>Text</dt><dd>{htmlIsEmpty(text) ? <span className="faint">Not written</span> : 'Written in the editor (.docx)'}</dd></>}
              <dt>Name</dt><dd>{values.document_name || <span className="faint">—</span>}</dd>
              <dt>Type</dt><dd>{labelOf(o.document_types, values.document_type) || <span className="faint">—</span>}</dd>
              <dt>Country</dt><dd>{labelOf(o.countries, values.country) || <span className="faint">—</span>}</dd>
              {(values.brand || values.therapeutic_area) && <>
                <dt>Brand · Area</dt><dd>{labelOf(o.brands, values.brand) || '—'} · {labelOf(o.therapeutic_areas, values.therapeutic_area) || '—'}</dd>
              </>}
              {o.is_admin && <><dt>Owner</dt><dd>{ownerLabel || 'You'}</dd></>}
            </dl>
            {chosen.length > 0 && (
              <div style={{ marginBottom: 14 }}>
                <div className="small muted row-tight"><ReceiptText size={13} /> {chosen.length} service{chosen.length === 1 ? '' : 's'} requested</div>
                <div className="up-est small"><span>Estimate</span><span>{inr(subtotal)}</span></div>
                <div className="up-est small muted"><span>GST (approx.)</span><span>{inr(gst)}</span></div>
                <div className="up-est"><strong>Total (approx.)</strong><strong>{inr(subtotal + gst)}</strong></div>
                <div className="tiny faint" style={{ marginTop: 4 }}>The final invoice is confirmed by Turacoz.</div>
              </div>
            )}
            <ul className="up-check">
              {checklist.map((c) => (
                <li key={c.label} className={c.done ? 'is-done' : ''}>
                  {c.done ? <CheckCircle2 size={14} /> : <span className="up-check-dot" />} {c.label}
                </li>
              ))}
            </ul>
          </div>
          <div className="panel-foot up-actions">
            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting ? <Spinner label="Uploading..." /> : <><Upload size={15} /> Upload Document</>}
            </button>
            <Link to="/content-lab-management/dashboard/" className="btn btn-ghost btn-block">Cancel</Link>
            {!ready && !submitting && <span className="small muted center">Complete the required fields to upload.</span>}
          </div>
        </aside>
      </form>
    </div>
  );
}
