/**
 * OnlyOffice editor — port of templates/documents/onlyoffice_edit.html (OnlyOfficeEditView,
 * URL /documents/onlyoffice/edit/?id=<version_id>). Standalone page, reachable without login
 * like the Django view. Comment events are collected and synced to
 * /api/viewer/comments/<id>/onlyoffice/save (2 s debounce) so they appear in the PDFTron preview.
 */
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, errorMessage, getToken } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useToast } from '@/components/ui';
import '../viewer.css';

interface EditConfig {
  config: any;
  file_name: string;
  document_title: string;
  onlyoffice_server_url: string;
  version_id: string;
  document_id: string;
  user_name: string;
}

interface OOComment { id: string; text: string; author: string; date: string; page: number; x: number; y: number; source: string }

function getDocumentType(fileExtension: string): string {
  const ext = (fileExtension || '').toLowerCase();
  if (['doc', 'docx', 'docm', 'dot', 'dotm', 'dotx', 'epub', 'fodt', 'htm', 'html', 'mht', 'odt', 'ott', 'pdf', 'rtf', 'txt', 'djvu', 'xps'].includes(ext)) return 'text';
  if (['xls', 'xlsx', 'xlsm', 'xlt', 'xltm', 'xltx', 'fods', 'ods', 'ots', 'csv'].includes(ext)) return 'spreadsheet';
  if (['pps', 'ppsx', 'ppsm', 'ppt', 'pptx', 'pptm', 'pot', 'potm', 'potx', 'fodp', 'odp', 'otp'].includes(ext)) return 'presentation';
  return 'text';
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[data-onlyoffice="${src}"]`);
    if (existing && (window as any).DocsAPI) { resolve(); return; }
    const s = document.createElement('script');
    s.src = src; s.async = true; s.dataset.onlyoffice = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('load failed'));
    document.body.appendChild(s);
  });
}

export default function OnlyOfficeEditPage() {
  const [search] = useSearchParams();
  const id = search.get('id') || '';
  const { user } = useAuth();
  const toast = useToast();
  const q = useQuery({
    queryKey: ['viewer', 'onlyoffice-config', id],
    queryFn: async () => (await api.get<EditConfig>('/api/viewer/onlyoffice/edit-config', { params: { id } })).data,
    retry: false, refetchOnWindowFocus: false,
  });
  const [error, setError] = useState<string | null>(null);
  const comments = useRef<OOComment[]>([]);
  const syncTimer = useRef<ReturnType<typeof setTimeout>>();
  const editorRef = useRef<any>(null);
  const started = useRef(false);
  const authorName = user ? (`${user.first_name} ${user.last_name}`.trim() || user.username) : '';
  const loggedIn = !!getToken();

  const versionId = q.data?.version_id;

  const syncCommentsToServer = async () => {
    if (!versionId || !loggedIn) return;
    try {
      await api.post(`/api/viewer/comments/${versionId}/onlyoffice/save`, { comments: comments.current });
    } catch { /* Failed to sync comments */ }
  };
  const debouncedSync = () => {
    clearTimeout(syncTimer.current);
    syncTimer.current = setTimeout(() => { void syncCommentsToServer(); }, 2000);
  };
  const commentCaptured = () => toast.info('Comment captured - will sync to preview');

  useEffect(() => {
    const data = q.data;
    if (!data || started.current) return;
    started.current = true;
    const serverUrl = data.onlyoffice_server_url;
    const vid = data.version_id;

    const onAddComment = (event: any) => {
      const c = event?.data || event;
      comments.current.push(c ? {
        id: c.guid || c.id || Date.now().toString(),
        text: c.text || c.comment || c.content || 'Comment added via OnlyOffice',
        author: c.author || c.user || authorName,
        date: new Date().toISOString(), page: c.page || 0, x: c.x || 100, y: c.y || 100, source: 'onlyoffice',
      } : {
        id: Date.now().toString(), text: 'Comment added in OnlyOffice (data not captured)', author: authorName,
        date: new Date().toISOString(), page: 0, x: 100, y: 100, source: 'onlyoffice',
      });
      commentCaptured();
      debouncedSync();
    };
    const onChangeCommentData = (event: any) => {
      const c = event?.data || event;
      if (!c) return;
      const idx = comments.current.findIndex((x) => x.id === c.guid || x.id === c.id);
      if (idx !== -1) {
        comments.current[idx].text = c.text || c.comment || comments.current[idx].text;
        comments.current[idx].date = new Date().toISOString();
      } else {
        comments.current.push({
          id: c.guid || c.id || Date.now().toString(), text: c.text || c.comment || 'Comment modified via OnlyOffice',
          author: c.author || c.user || authorName, date: new Date().toISOString(), page: c.page || 0,
          x: c.x || 100, y: c.y || 100, source: 'onlyoffice',
        });
        commentCaptured();
      }
      debouncedSync();
    };
    const onRemoveComment = (event: any) => {
      if (event?.data) {
        comments.current = comments.current.filter((c) => c.id !== event.data.guid);
        debouncedSync();
      }
    };
    const onRemoveComments = () => {
      comments.current = comments.current.filter((c) => c.source !== 'onlyoffice');
      debouncedSync();
    };
    // onDocumentReady → loadExistingComments(). In the template a scoping bug (ReferenceError on
    // `onlyofficeComments`) meant the loaded comments were never merged; only the requests were made.
    const onDocumentReady = async () => {
      if (!loggedIn) return;
      try {
        await api.get(`/api/viewer/comments/${vid}/onlyoffice`);
        await api.post(`/api/viewer/comments/${vid}/sync-to-onlyoffice`, {});
      } catch { /* ignore */ }
    };

    loadScript(`${serverUrl}/web-apps/apps/api/documents/api.js`).then(() => {
      try {
        const config = { ...data.config };
        if (!config || !config.document || !config.document.url) throw new Error('Invalid document configuration');
        config.width = '100%';
        config.height = '100%';
        config.documentType = getDocumentType(config.document.fileType);
        config.editorConfig = { ...config.editorConfig };
        config.editorConfig.customization = {
          ...(config.editorConfig.customization || {}),
          autosave: true, forcesave: true, logo: { image: '', imageEmbedded: '', url: '' }, customer: { name: 'TuraVector' },
        };
        config.events = {
          onDocumentStateChange: () => {}, onDocumentReady, onError: (event: any) => setError(`Document editor error: ${event?.data || 'Unknown error'}`),
          onRequestSaveAs: () => {}, onRequestInsertImage: () => {}, onRequestMailMergeRecipients: () => {},
          onRequestCompareFile: () => {}, onRequestEditRights: () => {}, onRequestHistory: () => {}, onRequestRestore: () => {},
          onAddComment, onChangeCommentData, onRemoveComment, onRemoveComments,
        };
        editorRef.current = new (window as any).DocsAPI.DocEditor('docEditor', config);
      } catch (err: any) {
        setError(`Error loading document editor: ${err?.message}`);
      }
    }).catch(() => {
      setError(`Failed to connect to OnlyOffice server at ${serverUrl}. The server may be down or inaccessible. Please contact your administrator.`);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data]);

  useEffect(() => () => {
    clearTimeout(syncTimer.current);
    try { editorRef.current?.destroyEditor?.(); } catch { /* ignore */ }
  }, []);

  const restore = async () => {
    if (!window.confirm('This will remove OnlyOffice synced annotations and restore only original PDFTron comments. Continue?')) return;
    try {
      await api.post(`/api/viewer/comments/${versionId}/restore`, {});
      window.alert('Original PDFTron comments restored successfully! Refresh the preview page to see them.');
    } catch {
      window.alert('Failed to restore comments');
    }
  };

  const loadError = q.error ? errorMessage(q.error) : null;
  return (
    <div className="oo-page">
      <div className="oo-header">
        <span className="grow center">TuraVector Document Editor{q.data?.document_title ? ` - ${q.data.document_title}` : ''}</span>
        <span className="row">
          <button className="btn btn-danger btn-sm" onClick={restore} disabled={!versionId}>Restore PDFTron Comments</button>
        </span>
      </div>
      <div className="oo-container">
        {loadError || error ? (
          <div className="notice notice-danger oo-message">{loadError || error}</div>
        ) : (
          <div id="docEditor" className="oo-editor">
            <div className="oo-message muted">Loading OnlyOffice Editor...</div>
          </div>
        )}
      </div>
    </div>
  );
}
