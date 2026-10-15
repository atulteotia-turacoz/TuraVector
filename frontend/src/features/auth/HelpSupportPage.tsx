/** Port of templates/documents/help_support.html (help_support_view + submit_support_request). */
import { useState, type FormEvent, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CircleHelp, Clock, Eye, LifeBuoy, ListChecks, Mail, Pencil, Phone, Send, Upload } from 'lucide-react';
import { api } from '@/lib/api';
import { Badge, ErrorNotice, Field, Loading, Modal, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import { apiError, timesince, truncatewords, useTimezoneAutoDetect } from './utils';
import './auth.css';

interface SupportRequest { id: number; subject: string; message: string; is_resolved: boolean; created_at: string }

type HelpKey = 'upload' | 'review' | 'annotation';

const HELP: Record<HelpKey, { title: string; body: ReactNode }> = {
  upload: {
    title: 'Document Upload Help',
    body: (
      <>
        <h3 className="small" style={{ fontWeight: 600 }}>Step-by-Step Guide:</h3>
        <ol>
          <li>Navigate to "Upload Document" from the sidebar</li>
          <li>Choose your document type and fill in metadata</li>
          <li>Select your file (PDF, DOCX, etc.)</li>
          <li>Add any additional information or tags</li>
          <li>Click "Upload" to submit</li>
        </ol>
        <div className="notice notice-accent"><strong>Tip:</strong> Make sure your document is properly formatted and all required metadata is filled before uploading.</div>
      </>
    ),
  },
  review: {
    title: 'Review Process Help',
    body: (
      <>
        <h3 className="small" style={{ fontWeight: 600 }}>Review Workflow:</h3>
        <ol>
          <li>Receive notification of assigned document</li>
          <li>Open document from your dashboard</li>
          <li>Use annotation tools to add feedback</li>
          <li>Submit review with recommendation</li>
          <li>Author receives feedback for revisions</li>
        </ol>
        <div className="notice notice-accent"><strong>Note:</strong> Reviews help maintain document quality and ensure compliance with guidelines.</div>
      </>
    ),
  },
  annotation: {
    title: 'Annotation Help',
    body: (
      <>
        <h3 className="small" style={{ fontWeight: 600 }}>Available Annotation Tools:</h3>
        <ul>
          <li><strong>Highlight:</strong> Select text and highlight important sections</li>
          <li><strong>Comments:</strong> Add detailed feedback and suggestions</li>
          <li><strong>Sticky Notes:</strong> Quick notes and reminders</li>
          <li><strong>Drawing:</strong> Freehand drawing for visual feedback</li>
        </ul>
        <div className="notice notice-accent"><strong>Tip:</strong> Use different colors and annotation types to organize your feedback effectively.</div>
      </>
    ),
  },
};

const QUICK: { key: HelpKey; icon: ReactNode; title: string; text: string }[] = [
  { key: 'upload', icon: <Upload size={20} />, title: 'Document Upload', text: 'Learn how to upload and manage documents' },
  { key: 'review', icon: <Eye size={20} />, title: 'Review Process', text: 'Understand the document review workflow' },
  { key: 'annotation', icon: <Pencil size={20} />, title: 'Annotations', text: 'How to add comments and annotations' },
];

const FAQ: [string, string][] = [
  ['How do I upload a document?', 'Navigate to the "Upload Document" section from the sidebar menu. Select your file (PDF, DOCX, etc.), fill in the required metadata, and click upload. The document will be processed and made available for review.'],
  ['How do I review a document?', "When a document is assigned to you for review, you'll receive a notification. Open the document from your dashboard, use the annotation tools to add comments and suggestions, then submit your review through the review panel."],
  ['What file formats are supported?', 'TuraVector supports PDF, DOCX, DOC, PPT, PPTX, and XLS files. For best compatibility and annotation features, we recommend using PDF format.'],
  ['How do I manage my notifications?', 'Click on the bell icon in the top navigation bar to view your notifications. You can also access the full notifications page from the user dropdown menu to see all your notification history.'],
];

export default function HelpSupportPage() {
  const toast = useToast();
  useTimezoneAutoDetect();
  const q = useQuery({
    queryKey: ['auth', 'help-support'],
    queryFn: async () => (await api.get('/api/documents/help-support')).data.support_requests as SupportRequest[],
  });
  const [help, setHelp] = useState<HelpKey | null>(null);
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [faq, setFaq] = useState<number | null>(null); // accordion: one item open at a time

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post('/api/documents/support', { subject, message });
      toast.success('Support request submitted successfully!');
      setSubject('');
      setMessage('');
      window.setTimeout(() => { void q.refetch(); }, 1500);
    } catch (err) {
      toast.error(`Error submitting request: ${apiError(err) || (err as Error)?.message || 'Failed to submit request'}`);
    } finally {
      setBusy(false);
    }
  };

  const requests = q.data ?? [];

  return (
    <div className="stack-lg">
      <PageHeader title="Help & Support" />

      <Panel title={<span className="row-tight"><CircleHelp size={15} /> Quick Help</span>}>
        <div className="grid-3">
          {QUICK.map((c) => (
            <button key={c.key} type="button" className="au-help-card" onClick={() => setHelp(c.key)}>
              <div className="au-option-icon">{c.icon}</div>
              <h3>{c.title}</h3>
              <p className="small muted">{c.text}</p>
            </button>
          ))}
        </div>
      </Panel>

      <div className="detail-grid">
        <Panel title={<span className="row-tight"><LifeBuoy size={15} /> Submit Support Request</span>}>
          <form className="stack" onSubmit={submit} id="supportRequestForm">
            <Field label="Subject" required>
              <input className="input" required maxLength={500} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Brief description of your issue" />
            </Field>
            <Field label="Message" required>
              <textarea className="input" rows={5} required value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Please provide detailed information about your issue..." />
            </Field>
            <div>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? <><Spinner /> Submitting...</> : <><Send size={14} /> Submit Request</>}
              </button>
            </div>
          </form>
        </Panel>

        <Panel title={<span className="row-tight"><Phone size={15} /> Contact Information</span>}>
          <div className="stack">
            <div>
              <strong>Email Support:</strong><br />
              <a href="mailto:support@turadome.com" className="row-tight" style={{ color: 'var(--accent)' }}><Mail size={13} /> support@turadome.com</a>
            </div>
            <div><strong>Response Time:</strong><br /><span className="muted">Usually within 24 hours</span></div>
            <div><strong>System Status:</strong><br /><Badge tone="ok">All systems operational</Badge></div>
          </div>
        </Panel>
      </div>

      {q.isLoading && <Loading />}
      {q.isError && <ErrorNotice error={q.error} />}
      {requests.length > 0 && (
        <Panel title={<span className="row-tight"><ListChecks size={15} /> Your Support Requests</span>} actions={<Badge tone="accent">{requests.length}</Badge>}>
          {requests.map((r) => (
            <div key={r.id} className="au-support-item">
              <div style={{ minWidth: 0 }}>
                <h3>{r.subject}</h3>
                <p>{truncatewords(r.message, 20)}</p>
                <span className="small faint row-tight"><Clock size={12} /> {timesince(r.created_at)} ago</span>
              </div>
              <div>{r.is_resolved ? <Badge tone="ok">Resolved</Badge> : <Badge tone="warn">Pending</Badge>}</div>
            </div>
          ))}
        </Panel>
      )}

      <Panel title={<span className="row-tight"><CircleHelp size={15} /> Frequently Asked Questions</span>}>
        <div className="au-faq">
          {FAQ.map(([question, answer], i) => (
            <details key={question} open={faq === i}>
              <summary onClick={(e) => { e.preventDefault(); setFaq((cur) => (cur === i ? null : i)); }}>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </Panel>

      <Modal open={help !== null} onClose={() => setHelp(null)} title={help ? HELP[help].title : ''}>
        <div className="au-help-body">{help && HELP[help].body}</div>
      </Modal>
    </div>
  );
}
