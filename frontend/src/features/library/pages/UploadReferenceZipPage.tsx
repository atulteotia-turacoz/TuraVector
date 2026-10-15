/** Port of templates/library/upload_reference_zip.html (library.views.upload_reference_zip_view). */
import { useRef, useState, type DragEvent, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Archive, ArrowLeft, CheckCircle2, CloudUpload, FileArchive, FolderOpen, Link2, Plus, ShieldCheck, Upload, X } from 'lucide-react';
import { api, toFormData } from '@/lib/api';
import { Empty, ErrorNotice, Field, Loading, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import { useActionFeedback, useLibraryPage } from '../api';
import '../library.css';

interface VersionOpt { id: number; version_number: string; document_name: string; document_number: string }
type Step = 'step1' | 'step2' | 'step3';

const MAX_SIZE = 50 * 1024 * 1024; // 50MB

/** formatFileSize() from the Django template */
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export default function UploadReferenceZipPage() {
  const toast = useToast();
  const feedback = useActionFeedback();
  const q = useLibraryPage<{ versions: VersionOpt[] }>(['zip-upload-options'], '/api/library/reference-zips/upload-options');
  const inputRef = useRef<HTMLInputElement>(null);
  const [versionId, setVersionId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>('step1');
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [versionInvalid, setVersionInvalid] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const versions = q.data!.versions;

  const clearFile = () => {
    if (inputRef.current) inputRef.current.value = '';
    setFile(null);
    setStep('step2');
  };

  const handleFileSelect = (f: File) => {
    if (!f.name.toLowerCase().endsWith('.zip')) {
      toast.error('Please select a ZIP file only.');
      clearFile();
      return;
    }
    if (f.size > MAX_SIZE) {
      toast.error(`File size must be less than 50MB. Your file is ${formatFileSize(f.size)}`);
      clearFile();
      return;
    }
    setFile(f);
    setStep('step3');
    toast.success('File selected successfully!');
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFileSelect(f);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!versionId) {
      toast.error('Please select a document version.');
      setVersionInvalid(true);
      setStep('step1');
      return;
    }
    if (!file) {
      toast.error('Please select a ZIP file to upload.');
      setStep('step2');
      return;
    }
    setProgress(0);
    try {
      const { data } = await api.post('/api/library/reference-zips/upload', toFormData({ version_id: versionId, zip_file: file }), {
        onUploadProgress: (ev) => { if (ev.total) setProgress(Math.round((ev.loaded / ev.total) * 100)); },
      });
      feedback.success(data, '/content-lab-management/reference-library/');
    } catch (err) {
      feedback.failure(err);
    } finally {
      setProgress(null);
    }
  };

  const order: Step[] = ['step1', 'step2', 'step3'];
  const stepCls = (s: Step) => (s === step ? 'is-active' : order.indexOf(s) < order.indexOf(step) ? 'is-done' : '');

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Reference ZIP"
        title="Upload Reference ZIP File"
        subtitle="Upload comprehensive reference document packages for your document versions"
      />

      <div className="lib-steps">
        <div className={`lib-step ${stepCls('step1')}`}><span className="lib-step-num">1</span> Select Document</div>
        <div className={`lib-step ${stepCls('step2')}`}><span className="lib-step-num">2</span> Choose ZIP File</div>
        <div className={`lib-step ${stepCls('step3')}`}><span className="lib-step-num">3</span> Upload</div>
      </div>

      <Panel>
        {versions.length === 0 ? (
          <Empty title="No Document Versions Available"
            action={<Link to="/content-lab-management/upload/" className="btn btn-primary"><Plus size={14} /> Create Your First Document</Link>}>
            You need to have at least one document with versions to upload reference ZIP files.
          </Empty>
        ) : (
          <form onSubmit={submit} noValidate className="stack-lg">
            <Field label="Select Document Version" required help="Select the document version that this reference ZIP file relates to">
              <select className={`input ${versionInvalid ? 'error' : ''}`} value={versionId} required
                onChange={(e) => {
                  setVersionId(e.target.value);
                  if (e.target.value) { setVersionInvalid(false); setStep('step2'); } else setStep('step1');
                }}>
                <option value="">Choose a document version...</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>{v.document_name} - {v.version_number} ({v.document_number})</option>
                ))}
              </select>
            </Field>

            <div>
              <span className="field-label">Reference ZIP File<span className="req">*</span></span>
              <div className={`dropzone ${over ? 'is-over' : ''}`} role="button" tabIndex={0}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
                onDragEnter={(e) => { e.preventDefault(); setOver(true); }}
                onDragOver={(e) => { e.preventDefault(); setOver(true); }}
                onDragLeave={(e) => { e.preventDefault(); setOver(false); }}
                onDrop={onDrop}>
                <CloudUpload size={32} className="faint" />
                <h3 className="serif" style={{ margin: '8px 0 4px' }}>Drag &amp; Drop your ZIP file here</h3>
                <p className="muted small">or click to browse files</p>
                <span className="btn btn-secondary btn-sm" style={{ marginTop: 10 }}><FolderOpen size={14} /> Choose File</span>
                <div className="tiny faint" style={{ marginTop: 10 }}>Only ZIP files • Max 50MB • Secure upload</div>
              </div>
              <input ref={inputRef} type="file" accept=".zip" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }} />
            </div>

            {file && (
              <div className="notice notice-ok between">
                <div className="row">
                  <FileArchive size={28} />
                  <div>
                    <div className="notice-title row-tight"><CheckCircle2 size={14} /> File Selected Successfully</div>
                    <div className="grid-2 small" style={{ gap: 24 }}>
                      <div><strong>File Name:</strong> <span style={{ wordBreak: 'break-all' }}>{file.name}</span></div>
                      <div><strong>File Size:</strong> {formatFileSize(file.size)}</div>
                    </div>
                  </div>
                </div>
                <button type="button" className="btn btn-ghost btn-icon" aria-label="Clear file" onClick={clearFile}><X size={14} /></button>
              </div>
            )}

            {progress !== null && (
              <div>
                <div className="between small"><span>Uploading...</span><span>{progress}%</span></div>
                <div className="lib-progress"><span style={{ width: `${progress}%` }} /></div>
              </div>
            )}

            <div className="between">
              <Link to="/content-lab-management/references/" className="btn btn-secondary"><ArrowLeft size={14} /> Back to References</Link>
              <button type="submit" className="btn btn-primary" disabled={progress !== null}>
                {progress !== null ? <><Spinner /> Uploading...</> : <><Upload size={14} /> Upload Reference ZIP</>}
              </button>
            </div>
          </form>
        )}
      </Panel>

      <div className="grid-3">
        <Panel>
          <div className="center stack">
            <Archive size={24} className="faint" />
            <h3 className="serif">What are ZIP References?</h3>
            <p className="muted small">Collections of supporting documents, citations, appendices, and related materials packaged together.</p>
          </div>
        </Panel>
        <Panel>
          <div className="center stack">
            <ShieldCheck size={24} className="faint" />
            <h3 className="serif">File Requirements</h3>
            <p className="muted small">ZIP files only, maximum 50MB. Organize your files clearly within the ZIP for easy access.</p>
          </div>
        </Panel>
        <Panel>
          <div className="center stack">
            <Link2 size={24} className="faint" />
            <h3 className="serif">Version Linking</h3>
            <p className="muted small">Each ZIP is linked to a specific document version, making it easy to track related materials.</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
