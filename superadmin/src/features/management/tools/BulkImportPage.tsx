import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, Download, Home, RotateCcw, Upload, UploadCloud, X, XCircle } from 'lucide-react';
import { api, downloadFile, errorMessage, toFormData } from '@/lib/api';
import { Field, PageHeader, Panel, Spinner, Stat, useToast } from '@/components/ui';
import { CATEGORY_META, type BulkResult, type CategoryKind } from './api';
import './tools.css';

/** documents/bulk_import.html + bulk_import_result.html */
export default function BulkImportPage({ kind }: { kind: CategoryKind }) {
  const meta = CATEGORY_META[kind];
  const toast = useToast();
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const errorsRef = useRef<HTMLDivElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);

  useEffect(() => {
    if (result?.errors.length) errorsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [result]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setFormError(null);
    try {
      const { data } = await api.post<BulkResult>(`/api/tools/bulk-import/${kind}`, toFormData({ file: file ?? undefined }));
      data.messages.forEach((m) => (m.level === 'success' ? toast.success(m.text) : toast.error(m.text)));
      qc.invalidateQueries({ queryKey: ['tools', 'categories', kind] });
      setResult(data);
    } catch (err) {
      setFormError(errorMessage(err));
    } finally { setBusy(false); }
  };

  const template = () => downloadFile(`/api/tools/bulk-import/${kind}/template`).catch((e) => toast.error(errorMessage(e)));

  if (result) {
    const tone = result.error_count === 0 ? 'ok' : result.success_count === 0 ? 'danger' : 'warn';
    return (
      <div className="tools-narrow stack-lg">
        <PageHeader title={`Import Results - ${result.import_type}`} />
        <div className={`notice notice-${tone}`}>
          {tone === 'ok' && <><div className="notice-title row-tight"><CheckCircle2 size={15} /> Import Completed Successfully!</div>All records were imported without errors.</>}
          {tone === 'danger' && <><div className="notice-title row-tight"><XCircle size={15} /> Import Failed</div>No records were imported due to errors.</>}
          {tone === 'warn' && <><div className="notice-title row-tight"><AlertTriangle size={15} /> Import Partially Successful</div>Some records were imported successfully, but there were errors with others.</>}
        </div>
        <div className="grid-2">
          <Stat value={result.success_count} label="Records Imported Successfully" />
          <Stat value={result.error_count} label="Records Failed" />
        </div>
        {result.errors.length > 0 && (
          <div ref={errorsRef}>
            <h3 className="section-title">Error Details</h3>
            <div className="tools-error-list">
              {result.errors.map((er, i) => <div key={i}><X size={12} style={{ display: 'inline', marginRight: 6 }} />{er}</div>)}
            </div>
          </div>
        )}
        <div className="row" style={{ justifyContent: 'center' }}>
          <button className="btn btn-primary" onClick={() => { setResult(null); setFile(null); }}><RotateCcw size={14} /> Import More</button>
          <Link className="btn btn-secondary" to="/"><Home size={14} /> Back to Dashboard</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="tools-narrow stack-lg">
      <PageHeader title={`Bulk Import ${meta.plural}`} />
      <div className="well">
        <div className="notice-title">Instructions:</div>
        <ol style={{ paddingLeft: 18 }}>
          <li>Download the CSV template using the button below</li>
          <li>Fill in your data following the template format</li>
          <li>Save the file as CSV or Excel format</li>
          <li>Upload the file using the form below</li>
          <li>Review the import results</li>
        </ol>
      </div>
      <Panel title="Download Template">
        <p className="muted" style={{ marginBottom: 12 }}>Download the template file to see the required format:</p>
        <button className="btn btn-secondary" onClick={template}><Download size={14} /> Download CSV Template</button>
      </Panel>
      <form onSubmit={submit} className="stack">
        <div
          className={`dropzone ${over ? 'is-over' : ''}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setOver(false); }}
          onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); }}
        >
          <UploadCloud size={30} style={{ margin: '0 auto 8px' }} />
          <div style={{ fontWeight: 600 }}>Drag and drop your file here or click to browse</div>
          <div className="small muted">Supported formats: CSV, Excel (XLSX, XLS)</div>
          <input ref={inputRef} type="file" hidden accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          {file && <div className="small" style={{ color: 'var(--ok)', marginTop: 10 }}><CheckCircle2 size={13} style={{ display: 'inline', marginRight: 4 }} />{file.name} selected</div>}
        </div>
        {formError && <Field error={formError}><span /></Field>}
        <div className="well small">
          <strong>File Requirements:</strong>
          <ul style={{ paddingLeft: 18, marginTop: 4 }}>
            <li>Maximum file size: 5 MB</li>
            <li>Encoding: UTF-8 for CSV files</li>
            <li>First row must contain column headers</li>
            <li>No empty rows between data</li>
          </ul>
        </div>
        <div className="row" style={{ justifyContent: 'center' }}>
          <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
            {busy ? <><Spinner /> Processing...</> : <><Upload size={15} /> Upload and Import</>}
          </button>
          <Link className="btn btn-secondary btn-lg" to="/"><X size={15} /> Cancel</Link>
        </div>
      </form>
    </div>
  );
}
