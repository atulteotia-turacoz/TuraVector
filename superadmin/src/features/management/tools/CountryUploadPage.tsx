import { useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Upload } from 'lucide-react';
import { api, errorMessage, toFormData } from '@/lib/api';
import { Field, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import type { FlashMessage } from './api';
import './tools.css';

const SAMPLE_CSV = 'name,code_name\n' +
  'United States,US\n' + 'United Kingdom,UK\n' + 'Canada,CA\n' + 'Australia,AU\n' + 'Germany,DE\n' + 'France,FR\n' +
  'Italy,IT\n' + 'Spain,ES\n' + 'Japan,JP\n' + 'China,CN\n' + 'India,IN\n' + 'Brazil,BR\n' + 'Mexico,MX\n' +
  'South Africa,ZA\n' + 'Russia,RU\n' + 'United States - East Coast,US\n' + 'United States - West Coast,US\n' +
  'United States - Central,US';

/** documents/categories/country_upload.html */
export default function CountryUploadPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [updateExisting, setUpdateExisting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const info = useQuery({
    queryKey: ['tools', 'country-upload'],
    queryFn: async () => (await api.get<{ sample_data: { name: string; code_name: string }[] }>('/api/tools/country-upload')).data,
  });

  const onPick = (f: File | undefined) => {
    if (!f) return;
    const ext = f.name.split('.').pop()!.toLowerCase();
    if (!['csv', 'xls', 'xlsx'].includes(ext)) {
      window.alert('Please select a valid file format (CSV, XLS, or XLSX)');
      if (inputRef.current) inputRef.current.value = '';
      setFile(null);
      return;
    }
    setFile(f);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const { data } = await api.post<{ messages: FlashMessage[] }>('/api/tools/country-upload',
        toFormData({ file: file ?? undefined, update_existing: updateExisting ? 'on' : undefined }));
      data.messages.forEach((m) => (m.level === 'success' ? toast.success(m.text) : toast.warning(m.text)));
      qc.invalidateQueries({ queryKey: ['tools', 'categories', 'countries'] });
      navigate('/documents/categories/countries/');
    } catch (err) {
      const msg = errorMessage(err);
      if (msg.startsWith('Missing required columns') || msg.startsWith('Error processing file')) toast.error(msg);
      else setError(msg);
    } finally { setBusy(false); }
  };

  const downloadSample = () => {
    const url = URL.createObjectURL(new Blob([SAMPLE_CSV], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = 'countries_sample.csv';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="tools-narrow stack-lg">
      <Link className="btn btn-ghost" to="/documents/categories/countries/"><ArrowLeft size={14} /> Back</Link>
      <PageHeader title="Upload Countries" />
      <div className="notice notice-accent">
        <div className="notice-title">File Requirements</div>
        <ul style={{ paddingLeft: 18 }}>
          <li>File format: Excel (.xlsx, .xls) or CSV (.csv)</li>
          <li>Required columns: <strong>name</strong>, <strong>code_name</strong></li>
          <li>Column names must match exactly (case-sensitive)</li>
          <li>Each row should contain a unique country name</li>
          <li>Country codes can be the same for different countries</li>
        </ul>
      </div>
      <Panel title="Upload Country Data">
        <form onSubmit={submit}>
          <Field label="Select File" help="Upload Excel (.xlsx, .xls) or CSV file. File should have columns: name, code_name" error={error}>
            <input ref={inputRef} type="file" className="input" accept=".csv,.xls,.xlsx" onChange={(e) => onPick(e.target.files?.[0])} />
          </Field>
          <div className="field">
            <label className="check">
              <input type="checkbox" checked={updateExisting} onChange={(e) => setUpdateExisting(e.target.checked)} />
              <span>Update existing countries<br /><span className="small muted">If checked, existing countries with same name will be updated</span></span>
            </label>
          </div>
          <button type="submit" className="btn btn-primary btn-block" disabled={busy} style={{ marginTop: 18 }}>
            {busy ? <Spinner /> : <Upload size={14} />} Upload File
          </button>
        </form>
      </Panel>
      <Panel title="Sample Data Format" flush>
        <table className="tbl">
          <thead><tr><th>name</th><th>code_name</th></tr></thead>
          <tbody>
            {(info.data?.sample_data || []).map((s) => <tr key={s.name}><td>{s.name}</td><td>{s.code_name}</td></tr>)}
          </tbody>
        </table>
      </Panel>
      <div className="notice notice-accent">
        <strong>Tip:</strong> You can download a sample file with the correct format to use as a template.{' '}
        <button className="act act-accent" onClick={downloadSample}>Download Sample CSV</button>
      </div>
    </div>
  );
}
