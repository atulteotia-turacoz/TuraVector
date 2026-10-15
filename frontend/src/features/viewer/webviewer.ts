/**
 * Apryse / PDFTron WebViewer helpers shared by the viewer pages.
 *
 * The Django templates loaded `static/dist/lib/webviewer.min.js`; here the npm
 * package is used with the runtime served from GET /api/config → PDFTRON_PATH.
 * Documents are loaded from authenticated backend endpoints, so the file
 * extension is passed explicitly (the URL has none).
 */
import type { WebViewerInstance, WebViewerOptions } from '@pdftron/webviewer';
import { api } from '@/lib/api';

export type { WebViewerInstance };

/** Create a WebViewer in `element`. Resolves to the instance. */
export async function createWebViewer(options: WebViewerOptions, element: HTMLElement): Promise<WebViewerInstance> {
  const mod = await import('@pdftron/webviewer');
  const WebViewer = (mod.default ?? mod) as unknown as (o: WebViewerOptions, el: HTMLElement) => Promise<WebViewerInstance>;
  return WebViewer(options, element);
}

/** Tear down a WebViewer created in `element` (removes its iframe). */
export function disposeWebViewer(instance: WebViewerInstance | null, element: HTMLElement | null) {
  try {
    (instance as any)?.UI?.dispose?.();
  } catch { /* ignore */ }
  if (element) element.innerHTML = '';
}

/**
 * preview_map.html `filterUnwantedComments` (v3.0): before loading, strip every
 * <link …>…</link> and <text …>…</text> annotation from the XFDF (regex, dot-all),
 * keeping everything else.
 */
export function filterUnwantedComments(xfdfString: string): string {
  if (!xfdfString || xfdfString.trim() === '') return xfdfString;
  try {
    let filtered = xfdfString;
    filtered = filtered.replace(/<link[^>]*>.*?<\/link>/gs, '');
    filtered = filtered.replace(/<text[^>]*>.*?<\/text>/gs, '');
    return filtered;
  } catch {
    return xfdfString;
  }
}

/** GET /api/viewer/annotations/:id/xfdf as text ('' on failure, like the Django retrievers). */
export async function fetchXfdf(versionId: number): Promise<string> {
  try {
    const res = await api.get(`/api/viewer/annotations/${versionId}/xfdf`, { responseType: 'text', transformResponse: (d) => d });
    return typeof res.data === 'string' ? res.data : '';
  } catch {
    return '';
  }
}

/** POST the current annotations (exportAnnotations({links, widgets})) to save-xfdf. */
export async function saveXfdf(instance: WebViewerInstance, versionId: number, documentId: number) {
  const { annotationManager } = instance.Core;
  const xfdfString = await annotationManager.exportAnnotations({ links: true, widgets: true });
  const { data } = await api.post(`/api/viewer/annotations/${versionId}/save-xfdf`, {
    xfdfData: xfdfString, docId: documentId, versionId,
  });
  return data as { message: string; file: string; annotations_count: number };
}

/**
 * preview_map.html `updateDocumentStats`: read the page count, retrying up to 5 × 500 ms
 * (Office documents report 0 pages for a while), then fall back to an estimate.
 */
export function pageCountWithRetry(instance: WebViewerInstance, fileExtension: string, set: (v: string) => void) {
  let retry = 0;
  const attempt = () => {
    const count = instance.Core.documentViewer.getPageCount();
    if (count > 0) { set(String(count)); return; }
    retry += 1;
    if (retry < 5) { setTimeout(attempt, 500); return; }
    const ext = (fileExtension || '').toLowerCase();
    if (['docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls'].includes(ext)) {
      let estimated = 1;
      if (ext.includes('doc')) estimated = 2;
      else if (ext.includes('ppt')) estimated = 5;
      else if (ext.includes('xls')) estimated = 1;
      set(`${estimated} (est.)`);
    } else {
      set('N/A');
    }
  };
  attempt();
}

/** Trigger a browser download of a Blob. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}
