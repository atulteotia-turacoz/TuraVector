/**
 * Reviewer page — port of templates/documents/review.html (documents.views.document_review_view,
 * URL /documents/review/?id=<version_id>).
 *
 * Opening the page marks the assignment as started (notifications + "Review Started" email, done by
 * the backend on GET). The WebViewer loads all annotations through /xfdf (unfiltered here, as in the
 * template), auto-saves 2 s after each change and every 30 s while annotations exist. Submitting the
 * review saves annotations once more, appends the annotation summary to the comments and posts the
 * decision (approved / revision / rejected).
 */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle, ArrowLeft, Check, CheckCircle2, ChevronDown, ChevronRight, ClipboardCheck, Clock, Download, Edit3,
  ExternalLink, Eye, EyeOff, FileText, Menu, RotateCcw, Save, Send, XCircle,
} from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { useUser } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { ErrorNotice, Field, Loading, Spinner, useToast } from '@/components/ui';
import {
  type ReferenceLink, type ViewerDocument, type ViewerReference, type ViewerVersion, WEBVIEWER_EXTENSIONS, fileUrl, inCsv,
  templateUserName, useClientConfig, usePageData,
} from '../api';
import { FullscreenButton, Office365Button, ViewerOverlay, useFullscreen } from '../components';
import { type WebViewerInstance, createWebViewer, disposeWebViewer, fetchXfdf, saveBlob, today } from '../webviewer';
import { titleCase, truncateChars } from './PreviewPage';
import '../viewer.css';

interface ReviewData {
  version: ViewerVersion;
  document: ViewerDocument;
  assignment: { id: number; started_at: string | null; review_date: string | null; is_completed: boolean } | null;
  references: ViewerReference[];
  linked_refs: ReferenceLink[];
  page_title: string;
}

function StatusPill({ status }: { status: number }) {
  if (status === 0) return <span className="badge"><Edit3 size={12} /> Draft</span>;
  if (status === 1) return <span className="badge badge-warn"><Clock size={12} /> Under Review</span>;
  if (status === 2) return <span className="badge badge-ok"><CheckCircle2 size={12} /> Approved</span>;
  if (status === 3) return <span className="badge badge-danger"><AlertCircle size={12} /> Needs Revision</span>;
  return null;
}

function Collapsible({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <section className="panel">
      <button type="button" className="panel-head vw-collapse-head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <h2 className="row">{icon} {title}</h2>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && <div className="panel-body">{children}</div>}
    </section>
  );
}

export default function ReviewPage() {
  const [search] = useSearchParams();
  const id = search.get('id');
  const user = useUser();
  const toast = useToast();
  const navigate = useNavigate();
  const configQ = useClientConfig();
  const q = usePageData<ReviewData>(['review', id], '/api/viewer/review', { id: id ?? '' });

  const viewerEl = useRef<HTMLDivElement>(null);
  const containerEl = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<WebViewerInstance | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [stats, setStats] = useState({ pages: '-', notes: 0, comments: 0, recent: 'No recent annotations' as React.ReactNode });
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [saveLabel, setSaveLabel] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [comments, setComments] = useState('');
  const [decision, setDecision] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { isFull, toggle: toggleFull } = useFullscreen(containerEl);

  const data = q.data;
  const config = configQ.data;
  const version = data?.version;
  const doc = data?.document;
  const canWebViewer = !!version?.has_file && inCsv(version.file_extension, WEBVIEWER_EXTENSIONS);

  const updateDocumentStats = useCallback(() => {
    const instance = instanceRef.current;
    if (!instance) return;
    try {
      const pageCount = instance.Core.documentViewer.getPageCount();
      const annotations = instance.Core.annotationManager.getAnnotationsList();
      const total = annotations.length;
      const commentsCount = annotations.filter((a: any) => a.getContents && (a.getContents() || '').trim().length > 0).length;
      const recent = total > 0
        ? <>Last updated: {new Date().toLocaleTimeString()}<br /><small>{total === 1 ? '1 annotation added' : `${total} annotations in document`}</small></>
        : 'No annotations yet';
      setStats({ pages: pageCount ? String(pageCount) : '-', notes: total, comments: commentsCount, recent });
    } catch { /* ignore */ }
  }, []);

  const saveAnnotationsDirectly = useCallback(async () => {
    const instance = instanceRef.current;
    if (!instance || !version || !doc) return;
    try {
      const xfdfString = await instance.Core.annotationManager.exportAnnotations({ links: true, widgets: true });
      try {
        await api.post(`/api/viewer/annotations/${version.id}/save-xfdf`, { xfdfData: xfdfString, docId: doc.id, versionId: version.id });
        toast.success('Annotations saved');
      } catch (err: any) {
        toast.error(`Save failed: ${err?.response?.data?.error || 'Unknown error'}`);
      }
    } catch {
      toast.error('Error saving annotations');
    }
  }, [version, doc, toast]);
  const saveRef = useRef(saveAnnotationsDirectly);
  saveRef.current = saveAnnotationsDirectly;

  useEffect(() => {
    if (!version || !doc || !config || !canWebViewer || !viewerEl.current) return;
    const element = viewerEl.current;
    let cancelled = false;
    let autoSave: ReturnType<typeof setTimeout> | undefined;
    if (!version.file_exists) {
      setLoadError(`The document file "${version.file_path}" was not found on the server (404).`);
      return;
    }
    const options: Record<string, unknown> = {
      path: config.PDFTRON_PATH, filename: version.file_title_name, isReadOnly: false, enableAnnotations: true,
      enableMeasurement: true, enableRedaction: false, fullAPI: true, preloadWorker: 'office',
    };
    if (config.PDFTRON_LICENSE_KEY) options.licenseKey = config.PDFTRON_LICENSE_KEY;

    createWebViewer(options as any, element).then((instance) => {
      if (cancelled) { disposeWebViewer(instance, element); return; }
      instanceRef.current = instance;
      const { documentViewer, annotationManager } = instance.Core as any;
      annotationManager.setCurrentUser(templateUserName(user));
      documentViewer.setDocumentXFDFRetriever(async () => fetchXfdf(version.id));
      documentViewer.addEventListener('documentLoaded', () => { setLoaded(true); updateDocumentStats(); });
      annotationManager.addEventListener('annotationChanged', (_a: any[], action: string) => {
        if (action === 'add' || action === 'modify' || action === 'delete') {
          clearTimeout(autoSave);
          autoSave = setTimeout(() => { void saveRef.current(); }, 2000);
          updateDocumentStats();
        }
      });
      const onError = () => setLoadError("We couldn't load the document preview.");
      documentViewer.addEventListener('documentLoadError', onError);
      (instance.UI as any).addEventListener?.('loaderror', onError);
      instance.UI.loadDocument(fileUrl(version.file_api), { filename: version.file_title_name, extension: version.file_extension });
    }).catch(() => { if (!cancelled) setLoadError("We couldn't load the document preview."); });

    // Auto-save every 30 seconds if there are annotations
    const interval = setInterval(() => {
      const inst = instanceRef.current;
      if (inst && inst.Core.annotationManager.getAnnotationsList().length > 0) void saveRef.current();
    }, 30000);
    const initialStats = setTimeout(updateDocumentStats, 1000);

    return () => {
      cancelled = true;
      clearTimeout(autoSave); clearInterval(interval); clearTimeout(initialStats);
      disposeWebViewer(instanceRef.current, element);
      instanceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version?.id, !!config, canWebViewer]);

  const onSaveClick = async () => {
    setSaveLabel('saving');
    try { await saveAnnotationsDirectly(); } finally {
      setSaveLabel('saved');
      setTimeout(() => setSaveLabel('idle'), 1000);
    }
  };

  const onExport = async () => {
    const instance = instanceRef.current;
    if (!instance || !version) return;
    try {
      const annotations = instance.Core.annotationManager.getAnnotationsList();
      if (annotations.length === 0) { window.alert('No annotations to export'); return; }
      const xfdf = await instance.Core.annotationManager.exportAnnotations({ links: true, widgets: true });
      saveBlob(new Blob([xfdf], { type: 'application/xml' }), `${version.file_title_name}_review_annotations_${today()}.xfdf`);
      toast.success('Annotations exported successfully!');
    } catch {
      toast.error('Export failed');
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!comments.trim()) { window.alert('Please enter review comments.'); return; }
    if (!decision) { window.alert('Please select a review decision.'); return; }
    const decisionText = decision === 'approved' ? 'approve' : decision === 'revision' ? 'request revision for' : 'reject';
    if (!window.confirm(`Are you sure you want to ${decisionText} this document?`)) return;

    let finalComments = comments;
    const instance = instanceRef.current;
    if (instance) {
      try {
        const annotations = instance.Core.annotationManager.getAnnotationsList();
        if (annotations.length > 0) {
          await saveAnnotationsDirectly();
          finalComments = `${comments}\n\n--- Review Annotations ---\nTotal annotations: ${annotations.length}\nAnnotations have been saved and are available in the document viewer.`;
          setComments(finalComments);
        }
      } catch { /* ignore */ }
    }
    setSubmitting(true);
    try {
      const { data: res } = await api.post('/api/viewer/review', { comments: finalComments, decision }, { params: { id } });
      (res.warnings || []).forEach((w: string) => toast.warning(w));
      toast.success(res.message);
      navigate(res.redirect || '/content-lab-management/reviewer-dashboard/');
    } catch (err) {
      toast.error(errorMessage(err));
      setSubmitting(false);
    }
  };

  if (q.isLoading || configQ.isLoading) return <Loading />;
  if (q.error) return (q.error.response?.data as any)?.redirect ? <Loading /> : <ErrorNotice error={q.error} />;
  if (configQ.error) return <ErrorNotice error={configQ.error} />;
  if (!data || !version || !doc || !config) return null;

  const ext = version.file_extension;
  const canDownloadOriginal = config.ALLOW_DOCUMENT_DOWNLOAD || user.is_superuser || user.is_manager
    || user.user_type === 'manager' || user.user_type === 'teacher'
    || user.user_type_code === 'manager' || user.user_type_code === 'teacher';

  return (
    <div className="vw-page">
      <header className="page-header">
        <div className="grow">
          <div className="eyebrow">{data.page_title}</div>
          <h1 className="truncate" title={doc.document_name}><ClipboardCheck size={20} /> {doc.document_name}</h1>
        </div>
        <div className="row">
          <StatusPill status={doc.stage_status} />
          <button className="btn btn-secondary btn-sm btn-icon" title={sidebarHidden ? 'Show Sidebar' : 'Hide Sidebar'}
            onClick={() => setSidebarHidden((v) => !v)}>
            <Menu size={14} />
          </button>
        </div>
      </header>

      <div className={`vw-layout ${sidebarHidden ? 'is-hidden' : ''}`}>
        <div className="vw-main">
          <section className="panel">
            <div className="panel-head">
              <h2 className="row"><FileText size={15} /> Document Viewer</h2>
              {version.has_file && (
                <div className="row">
                  <Office365Button versionId={version.id} />
                  <a href={fileUrl(version.file_api)} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm"><ExternalLink size={14} /> Open in New Tab</a>
                  <a href={fileUrl(version.file_api, true)} className="btn btn-secondary btn-sm"><Download size={14} /> Download</a>
                </div>
              )}
            </div>
            <div className="panel-body">
              {!version.has_file ? (
                <div className="empty"><h3>No File Available</h3><p className="muted">This document version doesn't have an associated file.</p></div>
              ) : canWebViewer ? (
                <div ref={containerEl} className={isFull ? 'vw-fullscreen' : ''}>
                  <div className="vw-toolbar">
                    <button className="btn btn-secondary btn-sm" onClick={onSaveClick} disabled={saveLabel !== 'idle'}>
                      {saveLabel === 'saving' ? <><Spinner /> Saving...</> : saveLabel === 'saved' ? <><Check size={14} /> Saved!</> : <><Save size={14} /> Save Annotations</>}
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={onExport}><Download size={14} /> Export</button>
                    <FullscreenButton isFull={isFull} onClick={toggleFull} />
                    {canDownloadOriginal && (
                      <a href={fileUrl(version.file_api, true)} className="btn btn-primary btn-sm"><Download size={14} /> Download Original</a>
                    )}
                  </div>
                  <div className="vw-viewer-wrap">
                    <div ref={viewerEl} className="vw-viewer" />
                    {(!loaded || loadError) && (
                      <ViewerOverlay>
                        {loadError ? (
                          <div className="stack center">
                            <div className="notice notice-danger"><div><div className="notice-title">Document Loading Failed</div>{loadError}</div></div>
                            <div className="row">
                              {version.file_exists && <a href={fileUrl(version.file_api, true)} className="btn btn-primary"><Download size={14} /> Download Document</a>}
                              <button className="btn btn-secondary" onClick={() => window.location.reload()}><RotateCcw size={14} /> Retry</button>
                            </div>
                          </div>
                        ) : (
                          <div className="stack center">
                            <Spinner label={`Loading ${(ext || '').toUpperCase()} document...`} />
                            <span className="muted small">This may take a moment for larger files</span>
                          </div>
                        )}
                      </ViewerOverlay>
                    )}
                  </div>
                </div>
              ) : ext === 'txt' || ext === 'rtf' ? (
                <TextPlaceholder version={version} />
              ) : (
                <div className="empty">
                  <FileText size={40} className="muted" />
                  <h3>{version.file_title_name}</h3>
                  <p className="muted">Preview not available for this file type ({ext})</p>
                  <div className="row center">
                    <a href={fileUrl(version.file_api)} target="_blank" rel="noreferrer" className="btn btn-primary"><ExternalLink size={14} /> Open File</a>
                    <a href={fileUrl(version.file_api, true)} className="btn btn-secondary"><Download size={14} /> Download File</a>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>

        {!sidebarHidden && (
          <aside className="vw-side stack-lg">
            <Collapsible title="Document Information" icon={<FileText size={15} />}>
              <dl className="kv">
                <dt>Document Number</dt><dd>{doc.document_number}</dd>
                <dt>Version</dt><dd>{version.version_number}</dd>
                <dt>Type</dt><dd>{doc.document_type || 'Not specified'}</dd>
                <dt>Created</dt><dd>{formatDateTime(version.created_at)}</dd>
                <dt>Owner</dt><dd>{doc.user.full_name || doc.user.username}</dd>
              </dl>
            </Collapsible>

            <Collapsible title="Document Stats" icon={<ClipboardCheck size={15} />}>
              <div className="grid-3 vw-stats">
                <div className="stat center"><div className="stat-value">{stats.pages}</div><div className="stat-label">Pages</div></div>
                <div className="stat center"><div className="stat-value">{stats.notes}</div><div className="stat-label">Notes</div></div>
                <div className="stat center"><div className="stat-value">{stats.comments}</div><div className="stat-label">Comments</div></div>
              </div>
              <hr className="hairline" />
              <h3 className="section-title">Recent Activity</h3>
              <div className="small muted">{stats.recent}</div>
            </Collapsible>

            {data.references.length > 0 && (
              <Collapsible title="Related References" icon={<Eye size={15} />}>
                <div className="stack">
                  {data.references.slice(0, 3).map((r) => (
                    <div key={r.id} className="between vw-ref">
                      <div className="grow">
                        <div className="vw-ref-title">{truncateChars(r.document_name, 35)}</div>
                        <div className="muted small">{r.reference_number}</div>
                        <div className="muted small">{titleCase(r.type)}</div>
                      </div>
                      <Link to={`/content-lab-management/reference-preview/${r.id}/`} className="btn btn-secondary btn-sm">View</Link>
                    </div>
                  ))}
                </div>
              </Collapsible>
            )}

            <Collapsible title="Review Actions" icon={<ClipboardCheck size={15} />}>
              <form onSubmit={onSubmit} className="stack">
                <Field label={<><Edit3 size={13} /> Review Comments</>} required help="Please provide detailed feedback about the document.">
                  <textarea className="input" rows={4} value={comments} onChange={(e) => setComments(e.target.value)}
                    placeholder="Enter your review comments here..." />
                </Field>
                <Field label="Review Decision" required>
                  <div className="stack">
                    {[
                      { v: 'approved', label: 'Approve Document', hint: 'Document meets all requirements', icon: <CheckCircle2 size={14} /> },
                      { v: 'revision', label: 'Request Revision', hint: 'Document needs modifications', icon: <Edit3 size={14} /> },
                      { v: 'rejected', label: 'Reject Document', hint: 'Document does not meet standards', icon: <XCircle size={14} /> },
                    ].map((o) => (
                      <label key={o.v} className="check vw-choice">
                        <input type="radio" name="decision" value={o.v} checked={decision === o.v} onChange={() => setDecision(o.v)} />
                        <span>
                          <strong className="row">{o.icon} {o.label}</strong>
                          <span className="muted small vw-block">{o.hint}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </Field>
                <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
                  {submitting ? <><Spinner /> Submitting...</> : <><Send size={14} /> Submit Review</>}
                </button>
                <Link to="/content-lab-management/reviewer-dashboard/" className="btn btn-secondary btn-block"><ArrowLeft size={14} /> Back to Dashboard</Link>
              </form>
            </Collapsible>
          </aside>
        )}
      </div>
    </div>
  );
}

/** review.html "Text Document" branch (placeholder text, as in the template). */
function TextPlaceholder({ version }: { version: ViewerVersion }) {
  const [state, setState] = useState<'hidden' | 'loading' | 'shown'>('hidden');
  const toggle = () => {
    if (state === 'shown') { setState('hidden'); return; }
    setState('loading');
    setTimeout(() => setState('shown'), 1000);
  };
  return (
    <div className="stack">
      <div className="notice notice-accent"><div><div className="notice-title">Text Document</div>{version.file_title_name}</div></div>
      <div className="well">
        <div className="center">
          <button className="btn btn-secondary" onClick={toggle} disabled={state === 'loading'}>
            {state === 'loading' ? <><Spinner /> Loading...</> : state === 'shown' ? <><EyeOff size={14} /> Hide Text Content</> : <><Eye size={14} /> Load Text Content</>}
          </button>
        </div>
        {state === 'shown' && (
          <div className="stack vw-mt">
            <div className="notice notice-accent"><div><strong>Text Content Preview:</strong><br />This would display the actual text content of the file.<br />
              <em>Implementation note: You would need to add a backend endpoint to extract and return the text content.</em></div></div>
            <pre className="mono small">{`Loading text content from: ${version.media_url ?? ''}

This is a placeholder for the actual text content.
In a full implementation, the backend would:
1. Read the text file
2. Return the content via an API endpoint
3. Display it here for review and annotation`}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
