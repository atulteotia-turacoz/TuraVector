/**
 * Reference preview — port of templates/documents/reference_preview.html
 * (documents.views.reference_preview, URLs /documents/reference-preview/<id>/ and /documents/reference-view/).
 *
 * The template read its flags with jQuery `.data()` and compared them to the string 'true'; jQuery
 * converts "true" to a boolean, so the watermark and print restrictions never applied on this page.
 * That effective behaviour is kept: a plain WebViewer, annotations are not loaded or saved.
 */
import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, Download, File, FileSpreadsheet, FileText, Info, Presentation } from 'lucide-react';
import { useUser } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { Badge, ErrorNotice, Loading, Panel, Spinner, useToast } from '@/components/ui';
import { type ViewerReference, WEBVIEWER_EXTENSIONS, fileUrl, inCsv, useClientConfig, usePageData } from '../api';
import { ViewerOverlay } from '../components';
import { type WebViewerInstance, createWebViewer, disposeWebViewer } from '../webviewer';
import '../viewer.css';

function ExtIcon({ ext }: { ext: string }) {
  if (ext === 'pdf') return <FileText size={15} />;
  if (inCsv(ext, 'doc,docx')) return <FileText size={15} />;
  if (inCsv(ext, 'xls,xlsx')) return <FileSpreadsheet size={15} />;
  if (inCsv(ext, 'ppt,pptx')) return <Presentation size={15} />;
  return <File size={15} />;
}

export default function ReferencePreviewPage() {
  const params = useParams();
  const [search] = useSearchParams();
  const referenceId = params.referenceId ?? search.get('id') ?? search.get('reference_id');
  useUser();
  const toast = useToast();
  const configQ = useClientConfig();
  const q = usePageData<{ reference: ViewerReference }>(['reference-preview', referenceId],
    referenceId ? `/api/viewer/references/${referenceId}/preview` : null);
  const viewerEl = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<WebViewerInstance | null>(null);
  const [state, setState] = useState<{ kind: 'loading' | 'ready' | 'error' | 'warn'; title?: string; text?: string }>({ kind: 'loading' });

  const reference = q.data?.reference;
  const config = configQ.data;
  const canView = !!reference?.has_file && inCsv(reference.file_extension, WEBVIEWER_EXTENSIONS);

  useEffect(() => {
    if (!reference || !config || !canView || !viewerEl.current) return;
    const element = viewerEl.current;
    let cancelled = false;
    if (!reference.file_exists) {
      setState({ kind: 'warn', title: 'Reference Access Issue',
        text: `The reference file "${reference.file_name}" was not found on the server (404). Please try downloading it directly.` });
      return;
    }
    fetch(fileUrl(reference.file_api), { method: 'HEAD' }).then((res) => {
      if (!res.ok && !cancelled) setState({ kind: 'warn', title: 'Reference Access Issue', text: 'The reference file may not be accessible. Please try downloading it directly.' });
    }).catch(() => {
      if (!cancelled) setState({ kind: 'warn', title: 'Reference Access Issue', text: 'The reference file may not be accessible. Please try downloading it directly.' });
    });
    const options: Record<string, unknown> = {
      path: config.PDFTRON_PATH, filename: reference.file_title_name, isReadOnly: false,
      licenseKey: config.PDFTRON_LICENSE_KEY || undefined, ui: 'default',
    };
    createWebViewer(options as any, element).then((instance) => {
      if (cancelled) { disposeWebViewer(instance, element); return; }
      instanceRef.current = instance;
      const { documentViewer } = instance.Core as any;
      documentViewer.addEventListener('documentLoaded', () => {
        setState({ kind: 'ready' });
        toast.success('Reference loaded successfully!');
      });
      const onError = (err: any) => {
        setState({ kind: 'error', title: 'Failed to load reference',
          text: `There was an error loading the reference file. Please try downloading it directly. Error: ${err?.message || 'Unknown error'}` });
        toast.error('Failed to load reference');
      };
      documentViewer.addEventListener('loaderror', onError);
      (instance.UI as any).addEventListener?.('loaderror', onError);
      instance.UI.loadDocument(fileUrl(reference.file_api), { filename: reference.file_title_name, extension: reference.file_extension });
    }).catch((error) => {
      if (cancelled) return;
      setState({ kind: 'error', title: 'Failed to initialize viewer',
        text: `Please try refreshing the page or download the reference directly. Error: ${error?.message || 'Unknown error'}` });
      toast.error('Failed to initialize reference viewer');
    });
    return () => {
      cancelled = true;
      disposeWebViewer(instanceRef.current, element);
      instanceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reference?.id, !!config, canView]);

  if (!referenceId) return <ErrorNotice error={new Error('No reference specified.')} title="Reference not found" />;
  if (q.isLoading || configQ.isLoading) return <Loading />;
  if (q.error) return (q.error.response?.data as any)?.redirect ? <Loading /> : <ErrorNotice error={q.error} />;
  if (configQ.error) return <ErrorNotice error={configQ.error} />;
  if (!reference || !config) return null;
  const ext = reference.file_extension;

  return (
    <div className="vw-page">
      <header className="page-header">
        <div className="grow">
          <div className="eyebrow">Reference Preview</div>
          <h1>{reference.reference_number}</h1>
          <p className="muted page-subtitle">{reference.document_name}</p>
          <div className="row wrap vw-mt">
            <Badge>{reference.type_display}</Badge>
            <Badge>{reference.subtype_display}</Badge>
            {reference.therapeutic_area && <Badge>{reference.therapeutic_area}</Badge>}
          </div>
        </div>
        {reference.ref_year && (
          <div className="right"><div className="stat-value">{reference.ref_year}</div><div className="small muted">Publication Year</div></div>
        )}
      </header>

      <div className="vw-layout">
        <div className="vw-main">
          {reference.has_file ? (
            <Panel title={<span className="row"><File size={15} /> {reference.file_title_name} <span className="muted small">Reference Preview</span></span>}>
              {canView ? (
                <>
                  <div className="vw-toolbar between">
                    <div>
                      <div className="row"><ExtIcon ext={ext} /> <strong>{(ext || '').toUpperCase()} Reference Viewer</strong></div>
                      <span className="muted small">Full annotation and viewing support</span>
                    </div>
                    <a href={fileUrl(reference.file_api, true)} className="btn btn-primary btn-sm"><Download size={14} /> Download Original</a>
                  </div>
                  <div className="vw-viewer-wrap">
                    <div ref={viewerEl} className="vw-viewer" />
                    {state.kind !== 'ready' && (
                      <ViewerOverlay>
                        {state.kind === 'loading' ? (
                          <div className="stack center">
                            <Spinner label={`Loading ${(ext || '').toUpperCase()} reference...`} />
                            <span className="muted small">This may take a moment for larger files</span>
                          </div>
                        ) : (
                          <div className={`notice ${state.kind === 'warn' ? 'notice-warn' : 'notice-danger'}`}>
                            <AlertTriangle size={16} /><div><div className="notice-title">{state.title}</div>{state.text}</div>
                          </div>
                        )}
                      </ViewerOverlay>
                    )}
                  </div>
                </>
              ) : (
                <div className="notice notice-warn">
                  <AlertTriangle size={16} /> Preview not available for this file type.{' '}
                  <a href={fileUrl(reference.file_api)} target="_blank" rel="noreferrer">Download file</a>
                </div>
              )}
            </Panel>
          ) : (
            <div className="notice notice-warn"><AlertTriangle size={16} /> No file attached to this reference.</div>
          )}
        </div>

        <aside className="vw-side stack-lg">
          <Panel title="Navigation">
            <div className="stack">
              <Link to="/content-lab-management/reference-library/" className="btn btn-secondary btn-sm btn-block"><ArrowLeft size={14} /> Back to Library</Link>
              <Link to={`/content-lab-management/reference-library/${reference.id}/`} className="btn btn-secondary btn-sm btn-block"><Info size={14} /> View Details</Link>
            </div>
          </Panel>
          <Panel title="Reference Information">
            <dl className="kv">
              <dt>Type</dt><dd>{reference.type_display}</dd>
              <dt>Subtype</dt><dd>{reference.subtype_display}</dd>
              <dt>Country</dt><dd>{reference.country}</dd>
              {reference.therapeutic_area && <><dt>Therapeutic Area</dt><dd>{reference.therapeutic_area}</dd></>}
              {reference.ref_year && <><dt>Year</dt><dd>{reference.ref_year}</dd></>}
            </dl>
          </Panel>
          <Panel title="Metadata">
            <dl className="kv">
              <dt>Created By</dt><dd>{reference.created_by ? (reference.created_by.full_name || reference.created_by.username) : ''}</dd>
              <dt>Created</dt><dd>{formatDateTime(reference.created_at)}</dd>
              <dt>Last Modified</dt><dd>{formatDateTime(reference.updated_at)}</dd>
              {reference.has_file && <><dt>File Type</dt><dd>{(ext || '').toUpperCase()}</dd></>}
            </dl>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
