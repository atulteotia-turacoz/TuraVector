/**
 * Simplified preview — port of templates/documents/preview_simple.html
 * (documents.views.document_preview_simple, URL /documents/preview-simple/<version_id>/).
 * No annotation persistence; watermark only when PDFTron is licensed; Retry, Office Online
 * fallback viewer, URL test and debug information as in the template.
 */
import { useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { AlertTriangle, Download, Eye, FileText, Info, RotateCcw } from 'lucide-react';
import { useUser } from '@/lib/auth';
import { fileSize } from '@/lib/format';
import { ErrorNotice, Loading, PageHeader, Panel, Spinner } from '@/components/ui';
import { type ViewerDocument, type ViewerVersion, fileUrl, useClientConfig, usePageData } from '../api';
import { Office365Button, ViewerOverlay } from '../components';
import { type WebViewerInstance, createWebViewer, disposeWebViewer } from '../webviewer';
import { authUrl } from '@/lib/api';
import '../viewer.css';

interface SimpleData { version: ViewerVersion; document: ViewerDocument; debug_info: { file_path: string | null; file_exists: boolean } }

export default function PreviewSimplePage() {
  const { versionId } = useParams();
  const [search] = useSearchParams();
  const notiId = search.get('noti_id');
  const user = useUser();
  const configQ = useClientConfig();
  const q = usePageData<SimpleData>(['preview-simple', versionId], `/api/viewer/versions/${versionId}/preview-simple`,
    notiId ? { noti_id: notiId } : undefined);
  const viewerEl = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<WebViewerInstance | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [fallback, setFallback] = useState(false);
  const [status, setStatus] = useState<{ kind: 'loading' | 'ready' | 'error'; text: string }>({ kind: 'loading', text: 'Initializing...' });

  const data = q.data;
  const config = configQ.data;
  const version = data?.version;

  useEffect(() => {
    if (!version || !config || fallback || !viewerEl.current) return;
    const element = viewerEl.current;
    const started = Date.now();
    let cancelled = false;
    const update = (text: string, kind: 'loading' | 'ready' | 'error' = 'loading') =>
      setStatus({ kind, text: kind === 'error' ? text : `${text} (${Math.round((Date.now() - started) / 1000)}s)` });
    update('Initializing PDFTron WebViewer...');
    const timeout = setTimeout(() => update('Document loading took too long. This may be due to a large file size or network issues.', 'error'), 20000);

    if (!version.file_exists) {
      clearTimeout(timeout);
      update(`Document file "${version.file_path}" was not found on the server (404).`, 'error');
      return;
    }
    const options: Record<string, unknown> = {
      path: config.PDFTRON_PATH, filename: version.file_title_name, enableAnnotations: true, enableMeasurement: false,
      enableRedaction: false, fullAPI: false, preloadWorker: 'office',
    };
    if (config.PDFTRON_LICENSE_KEY) options.licenseKey = config.PDFTRON_LICENSE_KEY;

    createWebViewer(options as any, element).then((instance) => {
      if (cancelled) { disposeWebViewer(instance, element); return; }
      instanceRef.current = instance;
      const { documentViewer, annotationManager, Annotations } = instance.Core as any;
      update('WebViewer initialized, loading document...');
      documentViewer.addEventListener('documentLoaded', () => {
        clearTimeout(timeout);
        const pageCount = documentViewer.getPageCount();
        update(`Document loaded successfully! (${pageCount} pages)`);
        setTimeout(() => setStatus((s) => ({ ...s, kind: 'ready' })), 1000);
        if (config.DOCUMENT_WATERMARK && config.PDFTRON_LICENSED) {
          for (let i = 1; i <= pageCount; i++) {
            const watermark = new Annotations.FreeTextAnnotation();
            watermark.PageNumber = i;
            watermark.X = 100; watermark.Y = 100; watermark.Width = 200; watermark.Height = 30;
            watermark.setContents(`${user.first_name} ${user.last_name}`);
            watermark.FontSize = '12px';
            watermark.setColor(new Annotations.Color(128, 128, 128, 0.5));
            watermark.ReadOnly = true;
            watermark.Listable = false;
            annotationManager.addAnnotation(watermark);
          }
          annotationManager.redrawAnnotations();
        }
      });
      const onError = (error: any) => { clearTimeout(timeout); update(`Document load error: ${error?.message || 'Unknown error'}`, 'error'); };
      documentViewer.addEventListener('documentLoadError', onError);
      (instance.UI as any).addEventListener?.('loaderror', onError);
      documentViewer.addEventListener('beginRendering', () => update('Rendering document pages...'));
      documentViewer.addEventListener('finishedRendering', () => update('Document rendering completed'));
      instance.UI.loadDocument(fileUrl(version.file_api), { filename: version.file_title_name, extension: version.file_extension });
    }).catch((error) => {
      if (cancelled) return;
      clearTimeout(timeout);
      update(`WebViewer initialization failed: ${error?.message || 'Unknown error'}`, 'error');
    });

    return () => {
      cancelled = true;
      clearTimeout(timeout);
      disposeWebViewer(instanceRef.current, element);
      instanceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version?.id, !!config, attempt, fallback]);

  const retry = () => { setFallback(false); setAttempt((n) => n + 1); };

  const testDocumentUrl = async () => {
    if (!version) return;
    try {
      const res = await fetch(fileUrl(version.file_api), { method: 'HEAD' });
      if (res.ok) window.alert(`✓ Document URL is accessible: ${version.media_url}`);
      else window.alert(`✗ Document URL failed: ${res.status} - ${res.statusText}`);
    } catch (error: any) {
      window.alert(`✗ Document URL test failed: ${error?.message}`);
    }
  };

  if (q.isLoading || configQ.isLoading) return <Loading />;
  if (q.error) return (q.error.response?.data as any)?.redirect ? <Loading /> : <ErrorNotice error={q.error} />;
  if (configQ.error) return <ErrorNotice error={configQ.error} />;
  if (!data || !version || !config) return null;

  const officeViewerUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(version.media_url || '')}`;

  return (
    <div className="vw-page">
      <PageHeader eyebrow="Document Preview" title={version.file_title_name}
        subtitle={<>Document Number: {data.document.document_number} | Version: {version.version_number} | Type: {(version.file_extension || '').toUpperCase()} | Size: {fileSize(version.file_size)}</>} />
      <Panel>
        <p className="small muted">
          <strong>Document URL:</strong>{' '}
          <a href={fileUrl(version.file_api)} target="_blank" rel="noreferrer">{version.media_url}</a>
          <button className="btn btn-secondary btn-sm vw-ml" onClick={testDocumentUrl}>Test URL</button>
        </p>
        <div className="row wrap vw-mt">
          <button className="btn btn-secondary" onClick={retry}><RotateCcw size={14} /> Retry Loading</button>
          <button className="btn btn-secondary" onClick={() => setFallback(true)}><Eye size={14} /> Alternative Viewer</button>
          <Office365Button versionId={version.id} label="Open in Office 365" busyLabel="Opening..." className="btn btn-primary" />
          <a href={fileUrl(version.file_api)} className="btn btn-primary"><Download size={14} /> Download Original</a>
          <a href={authUrl(`/api/viewer/versions/${version.id}/download-annotated`)} className="btn btn-secondary"><FileText size={14} /> Download with Annotations</a>
        </div>
      </Panel>

      <div className="vw-viewer-wrap vw-mt vw-tall">
        {fallback ? (
          <div className="stack">
            <div className="notice notice-ok"><Info size={16} /> Using Microsoft Office Online Viewer</div>
            <iframe title="Office Online Viewer" src={officeViewerUrl} className="viewer-frame" sandbox="allow-scripts allow-same-origin allow-forms" />
          </div>
        ) : (
          <>
            <div ref={viewerEl} key={attempt} className="vw-viewer vw-tall" />
            {status.kind !== 'ready' && (
              <ViewerOverlay>
                {status.kind === 'error' ? (
                  <div className="stack center">
                    <div className="notice notice-danger"><AlertTriangle size={16} /><div><div className="notice-title">Document Loading Failed</div>{status.text}</div></div>
                    <div className="row">
                      <button className="btn btn-primary" onClick={retry}><RotateCcw size={14} /> Retry</button>
                      <button className="btn btn-secondary" onClick={() => setFallback(true)}><Eye size={14} /> Alternative Viewer</button>
                    </div>
                  </div>
                ) : (
                  <div className="stack center">
                    <Spinner label="Loading Document..." />
                    <span className="muted small">Please wait while we load your {(version.file_extension || '').toUpperCase()} document</span>
                    <small className="muted">{status.text}</small>
                  </div>
                )}
              </ViewerOverlay>
            )}
          </>
        )}
      </div>

      {!config.PDFTRON_LICENSED && (
        <div className="notice notice-accent"><Info size={16} /> <span><strong>Trial Mode:</strong> PDFTron WebViewer is running in trial mode. A watermark will appear on the document.</span></div>
      )}
    </div>
  );
}
