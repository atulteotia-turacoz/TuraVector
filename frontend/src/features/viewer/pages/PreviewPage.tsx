/**
 * Document preview with Apryse/PDFTron WebViewer — port of templates/documents/preview_map.html
 * (Django view documents.views.document_preview, URL /documents/preview/<version_id>/).
 *
 * Behaviour kept from the template's JS:
 *  - annotations load through the XFDF retriever: OnlyOffice comments are synced first, then
 *    /xfdf is fetched and <text>/<link> annotations are filtered out (filterUnwantedComments);
 *  - annotation author = current user's name; createdAt / modifiedAt custom data;
 *  - auto-save 2 s after any add/modify/delete (also when annotations are imported on load);
 *  - read-only WebViewer for students/researchers while the version is under review;
 *  - download/print restrictions from settings, watermark "<user> - <version id>";
 *  - Recent Activity from AnnotationActivity rows, refreshed on load, after saves and on tab focus;
 *  - Send for Review / Revision / Complete buttons, Print, Fullscreen, collapsible sidebar.
 * Pieces of the template that were no-ops in practice (constructor `disableElements`, which is not a
 * WebViewer option; `setHeaderItems` that returned a new array; DOM de-duplication of elements living
 * inside the WebViewer iframe) are intentionally not reproduced.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Download, Edit3, FileText, FileUp, Link2, Lock, PlusCircle,
  Printer, RotateCcw, Save, Send,
} from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { useUser } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { ErrorNotice, Loading, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import {
  type ClientConfig, type ReferenceLink, type ViewerDocument, type ViewerReference, type ViewerVersion,
  WEBVIEWER_EXTENSIONS, fileUrl, inCsv, templateUserName, useClientConfig, usePageData,
} from '../api';
import { FullscreenButton, StageBadge, ViewerOverlay, useFullscreen } from '../components';
import {
  type WebViewerInstance, createWebViewer, disposeWebViewer, fetchXfdf, filterUnwantedComments, pageCountWithRetry,
  saveBlob, today,
} from '../webviewer';
import '../viewer.css';

interface PreviewData {
  version: ViewerVersion;
  document: ViewerDocument;
  references: ViewerReference[];
  linked_refs: ReferenceLink[];
}

interface Activity { user: string; action: string; type: string; timestamp: string; relative_time: string }

type LoadState =
  | { kind: 'loading'; largeKb?: number }
  | { kind: 'ready' }
  | { kind: 'fallback' }
  | { kind: 'error'; title: string; message?: string };

function readSidebarHidden(): boolean {
  try { return localStorage.getItem('sidebarHidden') === 'true'; } catch { return false; }
}
function writeSidebarHidden(v: boolean) {
  try { localStorage.setItem('sidebarHidden', v ? 'true' : 'false'); } catch { /* ignore */ }
}

export default function PreviewPage() {
  const { versionId } = useParams();
  const [search] = useSearchParams();
  const notiId = search.get('noti_id');
  const user = useUser();
  const toast = useToast();
  const navigate = useNavigate();
  const configQ = useClientConfig();
  const q = usePageData<PreviewData>(['preview', versionId], `/api/viewer/versions/${versionId}/preview`,
    notiId ? { noti_id: notiId } : undefined);

  const viewerEl = useRef<HTMLDivElement>(null);
  const cardEl = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<WebViewerInstance | null>(null);
  const [load, setLoad] = useState<LoadState>({ kind: 'loading' });
  const [pages, setPages] = useState('-');
  const [activities, setActivities] = useState<Activity[] | null>(null);
  const [activityError, setActivityError] = useState(false);
  const [sidebarHidden, setSidebarHidden] = useState(readSidebarHidden);
  const [busy, setBusy] = useState<string | null>(null);
  const [hideSendForReview, setHideSendForReview] = useState(false);
  const [stageOverride, setStageOverride] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const { isFull, toggle: toggleFull } = useFullscreen(cardEl);

  const data = q.data;
  const config = configQ.data;
  const version = data?.version;
  const document_ = data?.document;
  const userFullName = templateUserName(user);
  const isLocked = !!version && version.stage_status === 1 && inCsv(user.user_type, 'student,researcher');
  const isMgrTeacher = inCsv(user.user_type, 'manager,teacher') || user.is_manager;
  const canWebViewer = !!version?.has_file && inCsv(version.file_extension, WEBVIEWER_EXTENSIONS);

  // ------------------------------------------------------------------ activities (AnnotationActivity)
  const loadActivities = useCallback(async () => {
    if (!versionId) return;
    try {
      const { data: res } = await api.get(`/api/viewer/annotations/${versionId}/activities`);
      setActivities(res.activities || []);
      setActivityError(false);
    } catch {
      setActivityError(true);
    }
  }, [versionId]);

  // ------------------------------------------------------------------ save (saveAnnotationsDirectly)
  const saveAnnotationsDirectly = useCallback(async () => {
    const instance = instanceRef.current;
    if (!instance || !version || !document_) return;
    try {
      const xfdfString = await instance.Core.annotationManager.exportAnnotations({ links: true, widgets: true });
      try {
        await api.post(`/api/viewer/annotations/${version.id}/save-xfdf`, {
          xfdfData: xfdfString, docId: document_.id, versionId: version.id,
        });
        setTimeout(() => { void loadActivities(); }, 500);
        toast.success('Annotations saved');
      } catch (err: any) {
        const status = err?.response?.status;
        toast.error(`Save failed (${status ?? 'network'}: ${errorMessage(err)})`);
        window.alert(`Annotation save failed!\nStatus: ${status ?? ''}\nDetails: ${JSON.stringify(err?.response?.data ?? '').substring(0, 200)}...`);
      }
    } catch {
      toast.error('Error saving annotations');
    }
  }, [version, document_, loadActivities, toast]);
  const saveRef = useRef(saveAnnotationsDirectly);
  saveRef.current = saveAnnotationsDirectly;

  // ------------------------------------------------------------------ WebViewer
  useEffect(() => {
    if (!version || !document_ || !config || !canWebViewer || !viewerEl.current) return;
    const element = viewerEl.current;
    let cancelled = false;
    let loadingTimeout: ReturnType<typeof setTimeout> | undefined;
    let hardTimeout: ReturnType<typeof setTimeout> | undefined;
    let autoSaveTimeout: ReturnType<typeof setTimeout> | undefined;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const locked = isLocked;
    const cfg: ClientConfig = config;
    setLoad({ kind: 'loading' });

    if (!version.file_exists) {
      setLoad({ kind: 'error', title: 'Document Loading Failed',
        message: `The document file "${version.file_path}" was not found on the server (404).` });
      return;
    }

    // checkDocumentAccessibility(): HEAD the file, warn about very large files
    fetch(fileUrl(version.file_api), { method: 'HEAD' }).then((res) => {
      if (cancelled) return;
      if (!res.ok) {
        setLoad({ kind: 'error', title: 'Document Loading Failed', message: `We couldn't load the document preview (HTTP ${res.status}).` });
        return;
      }
      const len = Number(res.headers.get('content-length') || 0);
      const kb = Math.round(len / 1024);
      if (kb > 10240) setLoad((s) => (s.kind === 'loading' ? { kind: 'loading', largeKb: kb } : s));
    }).catch(() => {
      if (!cancelled) setLoad({ kind: 'error', title: 'Document Loading Failed', message: "We couldn't load the document preview." });
    });

    const syncOnlyOfficeCommentsToXFDF = async () => {
      try {
        const { data: res } = await api.get(`/api/viewer/comments/${version.id}/onlyoffice`);
        const comments = res.comments || [];
        if (comments.length > 0) {
          try {
            await api.post(`/api/viewer/comments/${version.id}/onlyoffice/save`, { comments });
            toast.success(`${comments.length} comment${comments.length > 1 ? 's' : ''} synced from edit mode`);
          } catch { /* Failed to sync OnlyOffice comments to XFDF */ }
        }
      } catch { /* ignore */ }
    };

    const options: Record<string, unknown> = {
      path: cfg.PDFTRON_PATH,
      filename: version.file_title_name,
      isReadOnly: locked,
      enableAnnotations: !locked,
      enableMeasurement: !locked,
      enableRedaction: false,
      fullAPI: true,
      preloadWorker: 'office',
    };
    if (cfg.PDFTRON_LICENSE_KEY) options.licenseKey = cfg.PDFTRON_LICENSE_KEY;

    createWebViewer(options as any, element).then((instance) => {
      if (cancelled) { disposeWebViewer(instance, element); return; }
      instanceRef.current = instance;
      const { documentViewer, annotationManager, Annotations } = instance.Core as any;
      const UI = instance.UI as any;

      annotationManager.setCurrentUser(userFullName);

      // applySecuritySettings
      try {
        if (!cfg.ALLOW_DOCUMENT_DOWNLOAD) {
          UI.disableElements(['downloadButton', 'saveAsButton']);
          UI.disableTools?.(['downloadButton', 'saveAsButton']);
        }
        if (cfg.DOCUMENT_PRINT_DISABLED) {
          UI.disableElements(['printButton']);
          UI.disableTools?.(['printButton']);
        }
      } catch { /* ignore */ }

      // one annotation popup at a time
      let activePopupAnnotation: any = null;
      try {
        UI.addEventListener('annotationPopupOpen', (e: any) => {
          const annotation = e?.detail?.annotation;
          if (activePopupAnnotation && annotation && activePopupAnnotation.Id !== annotation.Id) UI.closeElements(['annotationPopup']);
          activePopupAnnotation = annotation;
        });
        UI.addEventListener('annotationPopupClose', () => { activePopupAnnotation = null; });
      } catch { /* ignore */ }

      // debounce rapid selections; keep only the first selected text-markup annotation
      let lastSelection = 0;
      annotationManager.addEventListener('annotationSelected', (annotations: any[], action: string) => {
        const now = Date.now();
        if (now - lastSelection < 200) return;
        lastSelection = now;
        if (action === 'selected' && annotations.length > 0) {
          UI.closeElements(['annotationPopup']);
          const markup = annotations.filter((ann) =>
            ann instanceof Annotations.TextHighlightAnnotation || ann instanceof Annotations.TextUnderlineAnnotation ||
            ann instanceof Annotations.TextStrikeoutAnnotation || ann instanceof Annotations.TextSquigglyAnnotation);
          if (markup.length > 1) {
            annotationManager.deselectAllAnnotations();
            annotationManager.selectAnnotation(markup[0]);
          }
        }
      });

      // prevent duplicate replies within 500 ms
      const originalAddReply = annotationManager.createAnnotationReply;
      let lastReplyTime = 0;
      annotationManager.createAnnotationReply = function (annotation: any, replyText: string) {
        const now = Date.now();
        if (now - lastReplyTime < 500) return undefined;
        lastReplyTime = now;
        return originalAddReply.call(this, annotation, replyText);
      };

      // XFDF retriever (OnlyOffice comments synced first, then filtered XFDF)
      documentViewer.setDocumentXFDFRetriever(async () => {
        await syncOnlyOfficeCommentsToXFDF();
        const xfdf = await fetchXfdf(version.id);
        return filterUnwantedComments(xfdf);
      });

      const addWatermark = () => {
        documentViewer.addEventListener('documentLoaded', () => {
          timers.push(setTimeout(() => {
            const pageCount = documentViewer.getPageCount();
            if (pageCount === 0) return;
            for (let i = 1; i <= pageCount; i++) {
              const watermark = new Annotations.FreeTextAnnotation();
              watermark.PageNumber = i;
              watermark.X = 200; watermark.Y = 400; watermark.Width = 300; watermark.Height = 50;
              watermark.setContents(`${userFullName} - ${version.id}`);
              watermark.FontSize = '24px';
              watermark.setColor(new Annotations.Color(128, 128, 128, 0.3));
              watermark.Rotation = 45;
              watermark.ReadOnly = true;
              watermark.Listable = false;
              annotationManager.addAnnotation(watermark);
            }
            annotationManager.redrawAnnotations();
          }, 1000));
        });
      };

      const loadAnnotationTimestamps = async (annotations: any[]) => {
        try {
          const { data: res } = await api.get(`/api/viewer/annotations/${version.id}`);
          const rows = res.annotations || res || [];
          if (!Array.isArray(rows)) return;
          const map = new Map<string, any>();
          rows.forEach((db: any) => map.set(`${db.page}_${db.x}_${db.y}_${db.content}`, db));
          annotations.forEach((ann) => {
            const key = `${ann.PageNumber}_${Math.round(ann.X || 0)}_${Math.round(ann.Y || 0)}_${ann.Content || ''}`;
            const match = map.get(key);
            if (match && match.created_at) ann.setCustomData('createdAt', match.created_at);
          });
        } catch { /* ignore */ }
      };

      documentViewer.addEventListener('documentLoaded', () => {
        clearTimeout(loadingTimeout); clearTimeout(hardTimeout);
        setLoad({ kind: 'ready' });
        pageCountWithRetry(instance, version.file_extension, setPages);
        timers.push(setTimeout(() => {
          const loaded = annotationManager.getAnnotationsList();
          if (loaded.length > 0) {
            void loadAnnotationTimestamps(loaded).then(() => loadActivities());
          } else {
            void loadActivities();
          }
          void loadActivities();
        }, 1000));
        if (cfg.DOCUMENT_WATERMARK) addWatermark();
        toast.success('Document loaded successfully!');
      });
      documentViewer.addEventListener('pagesUpdated', () => pageCountWithRetry(instance, version.file_extension, setPages));
      documentViewer.addEventListener('layoutChanged', () => {
        timers.push(setTimeout(() => pageCountWithRetry(instance, version.file_extension, setPages), 100));
      });

      loadingTimeout = setTimeout(() => setLoad((s) => (s.kind === 'loading' ? { kind: 'fallback' } : s)), 10000);
      hardTimeout = setTimeout(() => setLoad((s) => (s.kind === 'ready' ? s
        : { kind: 'error', title: 'Document Loading Failed', message: "We couldn't load the document preview." })), 30000);

      annotationManager.addEventListener('annotationChanged', (annotations: any[], action: string) => {
        const processed = new Set<string>();
        annotations.forEach((annotation) => {
          if (processed.has(annotation.Id)) return;
          processed.add(annotation.Id);
          const now = new Date();
          if (action === 'add') {
            if (!annotation.Author || annotation.Author === '') {
              if (typeof annotation.setAuthor === 'function') annotation.setAuthor(userFullName);
              else annotation.Author = userFullName;
            }
            if (!annotation.getCustomData('createdAt')) annotation.setCustomData('createdAt', now.toISOString());
          } else if (action === 'modify') {
            annotation.setCustomData('modifiedAt', now.toISOString());
          }
        });
        if (action === 'add' || action === 'modify' || action === 'delete') {
          clearTimeout(autoSaveTimeout);
          autoSaveTimeout = setTimeout(() => { void saveRef.current(); }, 2000);
        }
      });

      const onLoadError = (err: any) => {
        clearTimeout(loadingTimeout); clearTimeout(hardTimeout);
        // WebViewer passes a string, an Error, or an event whose `detail` holds either
        const reason = (e: any): string => (typeof e === 'string' ? e : e instanceof Error ? e.message
          : e?.detail !== undefined ? reason(e.detail) : typeof e?.message === 'string' ? e.message : '');
        const detail = reason(err);
        setLoad({ kind: 'error', title: 'Failed to load document', message: detail ? `Error: ${detail}`
          : `This ${(version.file_extension || 'file').toUpperCase()} could not be opened — the file may be damaged or not a real ${(version.file_extension || '').toUpperCase()} file. Try downloading it, or upload a new version.` });
        toast.error('Failed to load document');
      };
      documentViewer.addEventListener('documentLoadError', onLoadError);
      UI.addEventListener?.('loaderror', onLoadError);

      UI.loadDocument(fileUrl(version.file_api), { filename: version.file_title_name, extension: version.file_extension });
    }).catch(() => {
      if (cancelled) return;
      setLoad({ kind: 'error', title: 'Failed to initialize viewer', message: 'Please try refreshing the page or download the document directly.' });
      toast.error('Failed to initialize document viewer');
    });

    const onVisibility = () => { if (!document.hidden) void loadActivities(); };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisibility);
      clearTimeout(loadingTimeout); clearTimeout(hardTimeout); clearTimeout(autoSaveTimeout);
      timers.forEach(clearTimeout);
      disposeWebViewer(instanceRef.current, element);
      instanceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version?.id, !!config, canWebViewer]);

  // ------------------------------------------------------------------ actions
  const onSave = async () => {
    if (!instanceRef.current) { toast.error('WebViewer not initialized - cannot save annotations'); return; }
    setBusy('save');
    try {
      await saveAnnotationsDirectly();
      toast.success('Annotations saved successfully!');
    } finally { setBusy(null); }
  };

  const workflow = async (kind: 'review' | 'revision' | 'complete') => {
    if (!version || !document_) return;
    const prompts = {
      review: 'Are you sure you want to send this document for review? This will change the status to "Under Review".',
      revision: 'Are you sure you want to send this document for revision? The document owner will be notified via email.',
      complete: 'Are you sure you want to mark this document as complete? The document owner will be notified via email.',
    };
    if (!window.confirm(prompts[kind])) return;
    const url = { review: '/api/doccore/workflow/send-for-review', revision: '/api/doccore/workflow/send-for-revision',
      complete: '/api/doccore/workflow/mark-complete' }[kind];
    setBusy(kind);
    try {
      const { data: result } = await api.post(url, { docId: document_.id, versionId: version.id });
      if (kind === 'review') {
        toast.success(`Document sent for review successfully! Status: ${result.status}.`);
        setStageOverride(1);
        setHideSendForReview(true);
        setTimeout(() => window.location.reload(), 2000);
      } else if (kind === 'revision') {
        toast.success(`Document sent for revision successfully! Status: ${result.status}. Email notification sent to document owner.`);
        setStageOverride(3);
        setTimeout(() => navigate('/content-lab-management/library/'), 3000);
      } else {
        toast.success(`Document marked as complete! Status: ${result.status}. Email notification sent to document owner.`);
        setStageOverride(2);
        setTimeout(() => navigate(`/content-lab-management/complete/?id=${version.id}`), 3000);
      }
    } catch (err) {
      const label = { review: 'send for review', revision: 'send for revision', complete: 'mark as complete' }[kind];
      toast.error(`Failed to ${label}: ${errorMessage(err)}`);
    } finally { setBusy(null); }
  };

  const exportAnnotations = async () => {
    const instance = instanceRef.current as any;
    if (!instance || !version) { toast.error('WebViewer not initialized'); return; }
    const { documentViewer, annotationManager } = instance.Core;
    const annotations = annotationManager.getAnnotationsList();
    if (annotations.length === 0 && !window.confirm('No annotations found. Do you want to download the document anyway?')) return;
    setExporting(true);
    try {
      if (instance.UI.downloadPdf) {
        try {
          instance.UI.downloadPdf({ includeAnnotations: true });
          toast.success('Document with annotations downloaded successfully!');
          return;
        } catch { /* fall back to manual export */ }
      }
      try {
        const doc = documentViewer.getDocument();
        const xfdfString = await annotationManager.exportAnnotations();
        const data = xfdfString && xfdfString.length > 0 ? await doc.getFileData({ xfdfString }) : await doc.getFileData();
        if (!data) throw new Error('No data received from document');
        const blob = new Blob([data instanceof ArrayBuffer ? data : new Uint8Array(data)], { type: 'application/pdf' });
        if (annotations.length > 0) {
          try { await api.post(`/api/viewer/save-pdf?version_id=${version.id}`, blob, { headers: { 'Content-Type': 'application/pdf' } }); } catch { /* ignore */ }
        }
        let filename = version.file_title_name;
        if (filename.includes('.')) filename = filename.substring(0, filename.lastIndexOf('.'));
        saveBlob(blob, `${filename}_annotated_${today()}.pdf`);
        const ext = (version.file_extension || '').toLowerCase();
        toast.success(`Document with annotations downloaded successfully${ext !== 'pdf' ? ` (converted from ${ext.toUpperCase()} to PDF)` : ''}!`);
      } catch (error: any) {
        try {
          const doc = documentViewer.getDocument();
          if (doc.downloadFile) { await doc.downloadFile(); toast.warning('Document downloaded! Note: Annotations may not be embedded.'); return; }
          const data = await doc.getFileData();
          saveBlob(new Blob([data], { type: 'application/pdf' }), `${version.file_title_name}_${today()}.pdf`);
          toast.warning('Document exported! Note: Annotations may not be embedded properly.');
        } catch (fallbackError: any) {
          const report = `\nExport Error Report\n==================\nOriginal Error: ${error?.message}\nFallback Error: ${fallbackError?.message}\nDocument Type: ${documentViewer.getDocument()?.getType?.() || 'unknown'}\nPage Count: ${documentViewer.getPageCount()}\nFile Extension: ${(version.file_extension || '').toLowerCase()}\nWebViewer Instance: Available\nAnnotation Count: ${annotationManager.getAnnotationsList().length}\n\nGenerated: ${new Date().toISOString()}\n                `;
          saveBlob(new Blob([report], { type: 'text/plain' }), `export_error_report_${today()}.txt`);
          toast.error('Failed to export annotated document: Export failed. Error report downloaded. Please check browser console for details.');
        }
      }
    } finally { setExporting(false); }
  };

  const printDocument = () => {
    const instance = instanceRef.current as any;
    if (!instance) { toast.error('WebViewer not initialized'); return; }
    if (config?.DOCUMENT_PRINT_DISABLED) { toast.warning('Printing is disabled for this document'); return; }
    instance.UI.print();
  };

  const toggleSidebar = (hidden: boolean) => { setSidebarHidden(hidden); writeSidebarHidden(hidden); };

  if (q.isLoading || configQ.isLoading) return <Loading />;
  if (q.error) return (q.error.response?.data as any)?.redirect ? <Loading /> : <ErrorNotice error={q.error} />;
  if (configQ.error) return <ErrorNotice error={configQ.error} />;
  if (!data || !version || !document_ || !config) return null;

  const stage = stageOverride ?? version.stage_status;
  const showStats = version.user_id === user.id || isMgrTeacher;
  const canDownloadUnsupported = config.ALLOW_DOCUMENT_DOWNLOAD || user.is_superuser || user.is_manager
    || user.user_type === 'manager' || user.user_type === 'teacher'
    || user.user_type_code === 'manager' || user.user_type_code === 'teacher';

  return (
    <div className="vw-page">
      <PageHeader eyebrow="Document Preview" title={version.file_title_name} subtitle={version.version_number} />
      <div className={`vw-layout ${sidebarHidden ? 'is-collapsed' : ''}`}>
        <div className="vw-main" ref={cardEl}>
          <section className={`panel ${isFull ? 'vw-fullscreen' : ''}`}>
            <div className="panel-body">
              {!version.has_file ? (
                <div className="notice notice-danger"><AlertTriangle size={16} /> File not found</div>
              ) : canWebViewer ? (
                <>
                  <div className="vw-toolbar">
                    {user.user_type === 'student' && stage === 0 && !hideSendForReview && (
                      <button className="btn btn-secondary btn-sm" disabled={busy === 'review'} onClick={() => workflow('review')}>
                        {busy === 'review' ? <><Spinner /> Sending...</> : <><Send size={14} /> Send for Review</>}
                      </button>
                    )}
                    {version.stage_status === 1 && inCsv(user.user_type, 'student,researcher') && (
                      <span className="btn btn-secondary btn-sm vw-static"><Lock size={14} /> Under Review</span>
                    )}
                    <button className="btn btn-primary btn-sm" onClick={onSave} disabled={busy === 'save'}>
                      {busy === 'save' ? <><Spinner /> Saving...</> : <><Save size={14} /> Save</>}
                    </button>
                    <DownloadMenu version={version} onExport={exportAnnotations} exporting={exporting} />
                    {isMgrTeacher && (
                      <>
                        <button className="btn btn-secondary btn-sm" disabled={busy === 'revision'} onClick={() => workflow('revision')}>
                          {busy === 'revision' ? <><Spinner /> Sending...</> : <><RotateCcw size={14} /> Revision</>}
                        </button>
                        <button className="btn btn-secondary btn-sm" disabled={busy === 'complete'} onClick={() => workflow('complete')}>
                          {busy === 'complete' ? <><Spinner /> Completing...</> : <><CheckCircle2 size={14} /> Complete</>}
                        </button>
                      </>
                    )}
                    <FullscreenButton isFull={isFull} onClick={toggleFull} />
                  </div>
                  <div className="vw-viewer-wrap">
                    <div ref={viewerEl} className="vw-viewer" />
                    {load.kind !== 'ready' && (
                      <ViewerOverlay>
                        <LoadPanel state={load} version={version} />
                      </ViewerOverlay>
                    )}
                  </div>
                </>
              ) : (
                <div className="notice notice-warn">
                  <AlertTriangle size={16} /> Preview not available for this file type.{' '}
                  {canDownloadUnsupported
                    ? <a href={fileUrl(version.file_api)} target="_blank" rel="noreferrer">Download file</a>
                    : <span className="muted">Contact administrator for access.</span>}
                </div>
              )}

              {(version.user_id === user.id || isMgrTeacher) && (
                <div className="row wrap vw-below">
                  {isLocked ? (
                    <>
                      <button className="btn btn-secondary" disabled title="Comments disabled - Document is under review"><Lock size={14} /> Comments Locked</button>
                      {!config.DOCUMENT_PRINT_DISABLED && (
                        <button className="btn btn-secondary" disabled title="Print disabled - Document is under review"><Lock size={14} /> Print Locked</button>
                      )}
                    </>
                  ) : (
                    <>
                      <Link to={`/content-lab-management/version/${version.id}/link-references/`} className="btn btn-secondary"><Link2 size={14} /> Link References</Link>
                      {!config.DOCUMENT_PRINT_DISABLED && (
                        <button className="btn btn-secondary" onClick={printDocument}><Printer size={14} /> Print</button>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>

        <aside className="vw-side">
          {sidebarHidden ? (
            <button className="btn btn-secondary btn-sm vw-side-expand" title="Show Sidebar" onClick={() => toggleSidebar(false)}>
              <ChevronLeft size={14} />
            </button>
          ) : (
            <div className="stack-lg">
              <button className="btn btn-secondary btn-sm btn-block" title="Hide Sidebar" onClick={() => toggleSidebar(true)}>
                <ChevronRight size={14} /> Hide Sidebar
              </button>
              <Panel title="Document Information">
                <dl className="kv">
                  <dt>Document Number</dt><dd>{document_.document_number}</dd>
                  <dt>Document Type</dt><dd>{document_.document_type}</dd>
                  <dt>Version</dt><dd>{version.version_number}</dd>
                  <dt>Status</dt><dd><StageBadge status={stage} /></dd>
                  <dt>Created</dt><dd>{formatDateTime(version.created_at)}</dd>
                  <dt>Modified</dt><dd>{formatDateTime(version.updated_at)}</dd>
                  <dt>Author</dt><dd>{document_.user.first_name} {document_.user.last_name}</dd>
                  <dt>Brand</dt><dd>{document_.brand}</dd>
                  <dt>Country</dt><dd>{document_.country}</dd>
                </dl>
              </Panel>

              {showStats && (
                <Panel title="Document Stats">
                  <div className="stat center">
                    <div className="stat-value">{pages}</div>
                    <div className="stat-label">Pages</div>
                  </div>
                  <hr className="hairline" />
                  <h3 className="section-title">Recent Activity</h3>
                  <div className="vw-activity small">
                    {activityError ? <div className="muted center">Error loading activities</div>
                      : !activities || activities.length === 0 ? <div className="muted center">No recent annotations</div>
                        : activities.map((a, i) => (
                          <div key={i} className="between vw-activity-row">
                            <span className="truncate">
                              {a.action === 'add' ? <PlusCircle size={13} className="status-accent" /> : <Edit3 size={13} className="status-accent" />}{' '}
                              <strong>{a.user}</strong> {a.action} {a.type}
                            </span>
                            <span className="muted nowrap" title={a.timestamp}>{a.relative_time}</span>
                          </div>
                        ))}
                  </div>
                </Panel>
              )}

              {data.references.length > 0 && (
                <Panel title="Related References">
                  <div className="stack">
                    {data.references.slice(0, 5).map((r) => (
                      <div key={r.id} className="between vw-ref">
                        <div className="grow">
                          <div className="vw-ref-title">{truncateChars(r.document_name, 40)}</div>
                          <div className="muted small">{r.reference_number}</div>
                          <div className="muted small">{titleCase(r.type)}</div>
                        </div>
                        <Link to={`/content-lab-management/reference-preview/${r.id}/`} className="btn btn-secondary btn-sm">View</Link>
                      </div>
                    ))}
                  </div>
                </Panel>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function DownloadMenu({ version, onExport, exporting }: { version: ViewerVersion; onExport: () => void; exporting: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);
  return (
    <div className="pop-wrap" ref={ref}>
      <button className="btn btn-primary btn-sm" onClick={() => setOpen((v) => !v)} disabled={exporting}>
        {exporting ? <><Spinner /> Preparing annotated document...</> : <><Download size={14} /> Download</>}
      </button>
      {open && (
        <div className="pop vw-pop">
          {version.has_file ? (
            <a className="pop-item" href={fileUrl(version.file_api, true)} onClick={() => setOpen(false)}>
              <FileText size={14} /> <span><span>Original Document</span><span className="muted tiny vw-block">Download without annotations</span></span>
            </a>
          ) : (
            <span className="pop-item muted"><FileText size={14} /> <span>No file available<span className="tiny vw-block">Document file missing</span></span></span>
          )}
          <div className="pop-sep" />
          <button className="pop-item" onClick={() => { setOpen(false); onExport(); }}>
            <FileText size={14} /> <span><span>With Annotations</span><span className="muted tiny vw-block">Export with all notes &amp; comments</span></span>
          </button>
        </div>
      )}
    </div>
  );
}

function LoadPanel({ state, version }: { state: LoadState; version: ViewerVersion }) {
  if (state.kind === 'loading') {
    if (state.largeKb) {
      return (
        <div className="stack center">
          <div className="notice notice-warn"><div><div className="notice-title">Large Document Detected</div>
            This document is {state.largeKb}KB. Loading may take several minutes.</div></div>
          <Spinner label="Please wait while we load your document..." />
        </div>
      );
    }
    return (
      <div className="stack center">
        <Spinner label={`Loading ${(version.file_extension || '').toUpperCase()} document...`} />
        <span className="muted small">This may take a moment for larger files</span>
      </div>
    );
  }
  if (state.kind === 'fallback') {
    return (
      <div className="stack center">
        <div className="notice notice-warn"><div><div className="notice-title">Document Preview Unavailable</div>
          The document preview is taking too long to load. Please try one of the options below:</div></div>
        <div className="row">
          <a href={fileUrl(version.file_api, true)} className="btn btn-primary"><Download size={14} /> Download Document</a>
          <button className="btn btn-secondary" onClick={() => window.location.reload()}><RotateCcw size={14} /> Retry Preview</button>
        </div>
      </div>
    );
  }
  if (state.kind === 'error') {
    return (
      <div className="stack center">
        <div className="notice notice-danger"><div><div className="notice-title">{state.title}</div>{state.message}</div></div>
        <div className="row">
          {version.file_exists && <a href={fileUrl(version.file_api, true)} className="btn btn-primary"><Download size={14} /> Download Document</a>}
          <button className="btn btn-secondary" onClick={() => window.location.reload()}><RotateCcw size={14} /> Retry</button>
        </div>
      </div>
    );
  }
  return null;
}

export function truncateChars(value: string, n: number): string {
  if (!value) return '';
  return value.length > n ? `${value.slice(0, n - 1)}…` : value;
}

export function titleCase(value: string): string {
  return (value || '').replace(/\w\S*/g, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
}
