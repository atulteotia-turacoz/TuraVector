/** Port of templates/library/upload_reference.html (library.views.upload_reference_view). */
import { useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Upload } from 'lucide-react';
import { api, toFormData } from '@/lib/api';
import { ErrorNotice, Field, Loading, PageHeader, Panel, Spinner } from '@/components/ui';
import { useActionFeedback, useLibraryPage, type Named } from '../api';
import '../library.css';

interface Options {
  countries: Named[];
  brands: Named[];
  therapeutic_areas: Named[];
  reference_types: [string, string][];
  reference_subtypes: [string, string][];
}

const MAX_SIZE = 10 * 1024 * 1024; // 10MB
const REQUIRED = ['reference_type', 'reference_subtype', 'document_name', 'country', 'reference_file'] as const;

export default function UploadReferencePage() {
  const feedback = useActionFeedback();
  const q = useLibraryPage<Options>(['reference-upload-options'], '/api/library/references/upload-options');
  const fileRef = useRef<HTMLInputElement>(null);
  const [values, setValues] = useState({
    reference_type: '', reference_subtype: '', document_name: '', country: '', therapeutic_area: '', ref_number: '', ref_year: '',
  });
  const [file, setFile] = useState<File | null>(null);
  const [invalid, setInvalid] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const o = q.data!;

  const set = (k: keyof typeof values) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [k]: e.target.value }));

  const onFile = (f: File | undefined) => {
    if (f && f.size > MAX_SIZE) {
      window.alert('File size must be less than 10MB');
      if (fileRef.current) fileRef.current.value = '';
      setFile(null);
      return;
    }
    setFile(f ?? null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const bad = new Set<string>();
    REQUIRED.forEach((k) => {
      const v = k === 'reference_file' ? (file ? 'x' : '') : values[k];
      if (!v.trim()) bad.add(k);
    });
    setInvalid(bad);
    if (bad.size) { window.alert('Please fill in all required fields'); return; }
    setBusy(true);
    try {
      const { data } = await api.post('/api/library/references/upload', toFormData({ ...values, reference_file: file }));
      feedback.success(data, '/content-lab-management/reference-library/');
    } catch (err) {
      feedback.failure(err);
    } finally {
      setBusy(false);
    }
  };

  const cls = (k: string) => `input ${invalid.has(k) ? 'error' : ''}`;

  return (
    <div className="stack-lg">
      <PageHeader title="Upload Reference Document" />
      <Panel title={<span className="row-tight"><Upload size={15} /> Upload Reference Document</span>}>
        <form onSubmit={submit} noValidate>
          <div className="form-grid">
            <Field label="Reference Type" required>
              <select className={cls('reference_type')} value={values.reference_type} onChange={set('reference_type')} required>
                <option value="">Select Reference Type</option>
                {o.reference_types.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Reference Subtype" required>
              <select className={cls('reference_subtype')} value={values.reference_subtype} onChange={set('reference_subtype')} required>
                <option value="">Select Reference Subtype</option>
                {o.reference_subtypes.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <div className="span-2">
              <Field label="Document Name" required>
                <input className={cls('document_name')} value={values.document_name} onChange={set('document_name')} required />
              </Field>
            </div>
            <Field label="Country" required>
              <select className={cls('country')} value={values.country} onChange={set('country')} required>
                <option value="">Select Country</option>
                {o.countries.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Therapeutic Area">
              <select className="input" value={values.therapeutic_area} onChange={set('therapeutic_area')}>
                <option value="">Select Therapeutic Area (Optional)</option>
                {o.therapeutic_areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </Field>
            <Field label="Reference Number">
              <input className="input" value={values.ref_number} onChange={set('ref_number')} placeholder="Optional reference number" />
            </Field>
            <Field label="Reference Year">
              <input className="input" type="number" min={1900} max={2099} value={values.ref_year} onChange={set('ref_year')} placeholder="Publication year" />
            </Field>
            <div className="span-2">
              <Field label="Reference File" required help="Supported file types: PDF, DOC, DOCX, TXT, RTF (Max size: 10MB)">
                <input ref={fileRef} className={cls('reference_file')} type="file" accept=".pdf,.doc,.docx,.txt,.rtf"
                  onChange={(e) => onFile(e.target.files?.[0])} required />
              </Field>
            </div>
          </div>
          <div className="between" style={{ marginTop: 20 }}>
            <Link to="/content-lab-management/reference-library/" className="btn btn-secondary"><ArrowLeft size={14} /> Back to Reference Library</Link>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? <Spinner /> : <Upload size={14} />} Upload Reference
            </button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
