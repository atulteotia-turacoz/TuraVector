/** templates/projects/upload_document.html */
import { useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Upload } from 'lucide-react';
import { api, errorMessage, toFormData } from '@/lib/api';
import { Field, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import { PageState, usePageData } from '../shared';

const MAX_SIZE = 50 * 1024 * 1024;

export default function UploadDocumentPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const back = `/journal-selector/projects/${projectId}/`;
  const q = usePageData<{ id: number; title: string }>(['projects', 'upload', projectId], `/api/projects/${projectId}/upload-document`, back);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  if (!q.data) return <PageState q={q} />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) { toast.error('Please enter a document title.'); return; }
    if (!file) { toast.error('Please select a file to upload.'); return; }
    if (file.size > MAX_SIZE) { toast.error('File size exceeds 50MB limit. Please choose a smaller file.'); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/api/projects/${projectId}/upload-document`, toFormData({ title, description, document_file: file }));
      toast.success(data.message);
      await qc.invalidateQueries({ queryKey: ['projects'] });
      navigate(back);
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div className="proj-narrow" style={{ maxWidth: 720 }}>
      <PageHeader title="Upload Document" />
      <Panel>
        <div className="well" style={{ marginBottom: 16 }}>
          <div className="small muted">Project</div>
          <strong>{q.data.title}</strong>
        </div>
        <form onSubmit={submit} className="stack">
          <Field label="Document Title" required help="Give your document a clear, descriptive title">
            <input className="input" required placeholder="Enter document title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Description" help="Provide a brief description of the document's content">
            <textarea className="input" rows={4} placeholder="Enter document description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <Field label="Document File" required help="Accepted formats: PDF, Word, Excel, PowerPoint, Text, CSV">
            <div className="row">
              <button type="button" className="btn btn-secondary" onClick={() => inputRef.current?.click()}><Upload size={14} /> Choose File</button>
              <span className="small muted">{file ? file.name : 'No file chosen'}</span>
              <input ref={inputRef} type="file" hidden accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
          </Field>
          <div className="row" style={{ marginTop: 6 }}>
            <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : <Upload size={14} />} Upload Document</button>
            <Link to={back} className="btn btn-secondary">Cancel</Link>
          </div>
        </form>
      </Panel>
    </div>
  );
}
