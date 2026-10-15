/** upload_document_view — documents/upload.html (/documents/upload-legacy/). */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Info, ShieldCheck, Upload } from 'lucide-react';
import { api, toFormData } from '@/lib/api';
import { ErrorNotice, Field, Loading, Modal, PageHeader, Panel, SearchSelect, Spinner } from '@/components/ui';
import { useDocPage, useSubmitHandlers } from '../shared';
import { useOwnerSearch } from './UploadPage';

interface Choice { value: number; label: string }
interface Options {
  is_admin: boolean; document_types: Choice[]; countries: Choice[]; brands: Choice[];
  therapeutic_areas: (Choice & { is_other: boolean })[];
}

const ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation';

export default function UploadLegacyPage() {
  const q = useDocPage<Options>(['upload-legacy-options'], '/api/doccore/upload-legacy/options');
  const { onSuccess, onError } = useSubmitHandlers();
  const ownerSearch = useOwnerSearch(!!q.data?.is_admin);
  const [owner, setOwner] = useState<string | number | null>(null);
  const [v, setV] = useState({ document_type: '', document_name: '', country: '', brand: '', therapeutic_area: '', therapeutic_area_other: '' });
  const [file, setFile] = useState<File | null>(null);
  const [fileInfo, setFileInfo] = useState('');
  const [uploading, setUploading] = useState(false);
  if (q.isLoading || q.redirecting) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const o = q.data!;
  const isOther = o.therapeutic_areas.find((t) => String(t.value) === v.therapeutic_area)?.is_other ?? false;
  const set = (k: keyof typeof v, val: string) => setV((s) => ({ ...s, [k]: val }));

  const onFile = (input: HTMLInputElement) => {
    const f = input.files?.[0];
    if (!f) return;
    if (f.size > 100 * 1024 * 1024) { window.alert('File size must be less than 100MB'); input.value = ''; setFile(null); return; }
    const ext = f.name.toLowerCase().split('.').pop() || '';
    if (!['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) {
      window.alert('Invalid file type. Please upload: PDF, DOC, DOCX, XLS, XLSX, PPT, or PPTX files only.');
      input.value = ''; setFile(null); return;
    }
    setFile(f);
    setFileInfo(`Selected: ${f.name} (${(f.size / 1024 / 1024).toFixed(2)} MB)`);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setUploading(true);
    try {
      const { data } = await api.post('/api/doccore/upload-legacy', toFormData({
        ...v, therapeutic_area_other: isOther ? v.therapeutic_area_other : '', document_owner: owner ?? '', document_file: file,
      }));
      onSuccess(data);
    } catch (err) {
      setUploading(false);
      onError(err);
    }
  };

  return (
    <div className="page-narrow stack-lg">
      <PageHeader title="Upload New Document" />
      <Panel title="Upload New Document">
        {o.is_admin && (
          <div className="notice notice-accent" style={{ marginBottom: 16 }}>
            <ShieldCheck size={15} /> <span><strong>Admin Mode:</strong> You can upload documents for other users by selecting a document owner below.</span>
          </div>
        )}
        <form onSubmit={submit} className="stack">
          {o.is_admin && (
            <Field label="Document Owner" help="Search and select who will own this document. If no owner is selected, you will be the owner.">
              <SearchSelect options={ownerSearch.withSelected(owner)} value={owner} onChange={setOwner}
                placeholder="Search users by name or email..." onSearch={ownerSearch.search} />
            </Field>
          )}
          <div className="form-grid">
            <Field label="Document Type" required>
              <select className="input" required value={v.document_type} onChange={(e) => set('document_type', e.target.value)}>
                <option value="">Select Document Type</option>
                {o.document_types.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </Field>
            <Field label="Document Name" required>
              <input className="input" required value={v.document_name} onChange={(e) => set('document_name', e.target.value)} />
            </Field>
            <Field label="Country" required>
              <select className="input" required value={v.country} onChange={(e) => set('country', e.target.value)}>
                <option value="">Select Country</option>
                {o.countries.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </Field>
            <Field label="Brand">
              <select className="input" value={v.brand} onChange={(e) => set('brand', e.target.value)}>
                <option value="">Select Brand</option>
                {o.brands.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </Field>
            <Field label="Therapeutic Area" required>
              <select className="input" required value={v.therapeutic_area}
                onChange={(e) => setV((s) => ({ ...s, therapeutic_area: e.target.value, therapeutic_area_other: '' }))}>
                <option value="">Select Therapeutic Area</option>
                {o.therapeutic_areas.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </Field>
            {isOther && (
              <Field label="Please Specify Other Therapeutic Area" required
                help={<span className="row-tight"><Info size={12} /> Please specify the therapeutic area that is not listed above.</span>}>
                <input className="input" required maxLength={255} placeholder="Enter therapeutic area name"
                  value={v.therapeutic_area_other} onChange={(e) => set('therapeutic_area_other', e.target.value)} />
              </Field>
            )}
          </div>
          <Field label="Document File" required
            help={<><strong>Supported formats:</strong> PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX<br /><strong>Maximum file size:</strong> 100MB</>}>
            <input type="file" className="input" required accept={ACCEPT} onChange={(e) => onFile(e.target)} />
          </Field>
          {file && <div className="dc-file-picked">{fileInfo}</div>}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <Link to="/content-lab-management/dashboard/" className="btn btn-secondary">Cancel</Link>
            <button type="submit" className="btn btn-primary"><Upload size={14} /> Upload Document</button>
          </div>
        </form>
      </Panel>
      <Modal open={uploading} onClose={() => undefined} title="Uploading Document">
        <div className="center stack">
          <Spinner />
          <p>Please wait while your document is being uploaded...</p>
        </div>
      </Modal>
    </div>
  );
}
