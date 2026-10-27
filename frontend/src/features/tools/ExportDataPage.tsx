import { useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Download, Info } from 'lucide-react';
import { api, errorMessage, toFormData } from '@/lib/api';
import { ErrorNotice, Loading, PageHeader, Panel, Spinner, Stat, useToast } from '@/components/ui';
import './tools.css';

const TYPES: [string, string, string][] = [
  ['all', 'All Data', 'Export all your documents and saved journals'],
  ['documents', 'Documents Only', 'Export only your document records'],
  ['journals', 'Saved Journals Only', 'Export only your saved journal selections'],
];
const FORMATS: [string, string, string][] = [
  ['json', 'JSON', 'Machine-readable format, ideal for data processing'],
  ['csv', 'CSV', 'Excel-compatible format for spreadsheet analysis'],
];

function Radio({ name, value, checked, onChange, title, note }: { name: string; value: string; checked: boolean; onChange: (v: string) => void; title: ReactNode; note: string }) {
  return (
    <label className={`tools-radio ${checked ? 'is-checked' : ''}`}>
      <input type="radio" name={name} value={value} checked={checked} onChange={() => onChange(value)} />
      <span><strong>{title}</strong><br /><span className="small muted">{note}</span></span>
    </label>
  );
}

/** documents/export_data.html */
export default function ExportDataPage() {
  const toast = useToast();
  const [type, setType] = useState('all');
  const [format, setFormat] = useState('json');
  const [busy, setBusy] = useState(false);
  const q = useQuery({
    queryKey: ['tools', 'export-summary'],
    queryFn: async () => (await api.get<{ documents_count: number; journals_count: number }>('/api/tools/export-data')).data,
  });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await api.post('/api/tools/export-data', toFormData({ export_type: type, export_format: format }), { responseType: 'blob' });
      const cd: string = res.headers['content-disposition'] || '';
      const m = /filename="?([^";]+)"?/i.exec(cd);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url; a.download = m ? m[1] : `turavector_export.${format}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  return (
    <div className="tools-narrow stack-lg" style={{ maxWidth: 860 }}>
      <PageHeader title="Export Data" />
      <Panel title="Your Data Summary">
        <div className="grid-3">
          <Stat value={d.documents_count} label="Documents" />
          <Stat value={d.journals_count} label="Saved Journals" />
        </div>
      </Panel>
      <Panel title="Export Options">
        <div className="notice notice-accent row-tight" style={{ marginBottom: 18 }}><Info size={14} /> Select the data you want to export and choose your preferred format.</div>
        <form onSubmit={submit}>
          <h3 className="section-title" style={{ marginTop: 0 }}>What to Export</h3>
          {TYPES.map(([v, t, n]) => <Radio key={v} name="export_type" value={v} checked={type === v} onChange={setType} title={t} note={n} />)}
          <h3 className="section-title">Export Format</h3>
          {FORMATS.map(([v, t, n]) => <Radio key={v} name="export_format" value={v} checked={format === v} onChange={setFormat} title={t} note={n} />)}
          <div className="row" style={{ marginTop: 22 }}>
            <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : <Download size={14} />} Export Data</button>
            <Link className="btn btn-secondary" to="/journal-selector/dashboard/">Cancel</Link>
          </div>
        </form>
      </Panel>
    </div>
  );
}
