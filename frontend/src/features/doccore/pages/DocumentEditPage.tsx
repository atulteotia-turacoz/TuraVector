/** document_edit — documents/document_edit.html */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Info, Save, X } from 'lucide-react';
import { api } from '@/lib/api';
import { ErrorNotice, Field, Loading, PageHeader, Panel } from '@/components/ui';
import { Stage, useDocPage, useSubmitHandlers } from '../shared';

interface Choice { value: number; label: string }
interface Data {
  title: string;
  document: {
    id: number; document_name: string; document_number: string; document_type: number; country: number; country_name: string;
    brand: number | null; therapeutic_area: number | null; latest_version_status: number; versions_count: number; owner_name: string;
  };
  document_types: Choice[]; countries: Choice[]; brands: Choice[]; therapeutic_areas: Choice[];
}

export default function DocumentEditPage() {
  const { documentId } = useParams();
  const q = useDocPage<Data>(['edit', documentId], `/api/doccore/documents/${documentId}/edit`);
  const { onSuccess, onError } = useSubmitHandlers();
  const [v, setV] = useState({ document_name: '', document_type: '', country: '', brand: '', therapeutic_area: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [invalid, setInvalid] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (!q.data) return;
    const doc = q.data.document;
    setV({
      document_name: doc.document_name,
      document_type: String(doc.document_type ?? ''),
      country: String(doc.country ?? ''),
      brand: doc.brand ? String(doc.brand) : '',
      therapeutic_area: doc.therapeutic_area ? String(doc.therapeutic_area) : '',
    });
  }, [q.data]);
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const doc = d.document;
  const set = (k: keyof typeof v, val: string) => { setV((s) => ({ ...s, [k]: val })); setInvalid((s) => ({ ...s, [k]: false })); };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const missing: Record<string, boolean> = {};
    (['document_name', 'document_type', 'country'] as const).forEach((k) => { if (!v[k]) missing[k] = true; });
    if (Object.keys(missing).length) { setInvalid(missing); window.alert('Please fill in all required fields.'); return; }
    setErrors({});
    try {
      const { data } = await api.post(`/api/doccore/documents/${doc.id}/edit`, v);
      onSuccess(data);
    } catch (err) {
      onError(err, setErrors);
    }
  };

  const opts = (list: Choice[], empty: string) => (
    <>
      <option value="">{empty}</option>
      {list.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
    </>
  );

  return (
    <div className="page-narrow stack-lg">
      <div><Link to={`/content-lab-management/document/${doc.id}/`} className="btn btn-ghost"><ArrowLeft size={14} /> Back to Document Details</Link></div>
      <PageHeader title="Edit Document Details" subtitle="Update the basic information for this document. These changes will affect the document record but not its file versions." eyebrow={d.title} />
      <Panel>
        <form onSubmit={submit} className="stack">
          <Field label="Document Name" required error={errors.document_name} help="The main title/name of this document">
            <input className="input" required maxLength={500} placeholder="Enter document name" value={v.document_name}
              aria-invalid={invalid.document_name || undefined} onChange={(e) => set('document_name', e.target.value)} />
          </Field>
          <div className="form-grid">
            <Field label="Document Type" required error={errors.document_type}>
              <select className="input" required value={v.document_type} aria-invalid={invalid.document_type || undefined}
                onChange={(e) => set('document_type', e.target.value)}>{opts(d.document_types, '---------')}</select>
            </Field>
            <Field label="Country" required error={errors.country} help={`Currently selected: ${doc.country_name}`}>
              <select className="input" required value={v.country} aria-invalid={invalid.country || undefined}
                onChange={(e) => set('country', e.target.value)}>{opts(d.countries, '---------')}</select>
            </Field>
            <Field label="Brand" error={errors.brand} help="Select the brand associated with this document (optional)">
              <select className="input" value={v.brand} onChange={(e) => set('brand', e.target.value)}>{opts(d.brands, '-- Select Brand (Optional) --')}</select>
            </Field>
            <Field label="Therapeutic Area" error={errors.therapeutic_area} help="Select the therapeutic area this document relates to (optional)">
              <select className="input" value={v.therapeutic_area} onChange={(e) => set('therapeutic_area', e.target.value)}>
                {opts(d.therapeutic_areas, '-- Select Therapeutic Area (Optional) --')}
              </select>
            </Field>
          </div>
          <div className="between">
            <Link to={`/content-lab-management/document/${doc.id}/`} className="btn btn-secondary"><X size={14} /> Cancel</Link>
            <button type="submit" className="btn btn-primary"><Save size={14} /> Save Changes</button>
          </div>
        </form>
      </Panel>

      <Panel title={<span className="row-tight"><Info size={15} /> Current Document Information</span>}>
        <div className="grid-2">
          <dl className="kv">
            <dt>Document Number:</dt><dd>{doc.document_number}</dd>
            <dt>Current Status:</dt><dd><Stage value={doc.latest_version_status} /></dd>
          </dl>
          <dl className="kv">
            <dt>Total Versions:</dt><dd>{doc.versions_count}</dd>
            <dt>Owner:</dt><dd>{doc.owner_name}</dd>
          </dl>
        </div>
      </Panel>

      <div className="notice notice-accent">
        <Info size={15} /> <span><strong>Note:</strong> Changing document details will not affect existing file versions. File content changes should be done through version editing or by creating new versions.</span>
      </div>
    </div>
  );
}
