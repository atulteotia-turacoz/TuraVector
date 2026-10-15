/**
 * Shared helpers for the doccore feature (document lifecycle pages).
 *
 * Backend page endpoints answer a Django "messages.error + redirect" with an HTTP error whose
 * `detail` is `{ message, redirect, level }`; `useDocPage` turns that into a toast + navigation.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { FileText, Lock, RefreshCw } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Modal, StageStatus, useToast } from '@/components/ui';
import './doccore.css';

export interface UserBrief {
  id: number; username: string; email: string; first_name: string; last_name: string;
  full_name: string; user_type: string; user_type_title: string;
}

export interface RedirectDetail { message?: string | null; redirect?: string; level?: string; errors?: Record<string, string> }

function detailOf(err: unknown): RedirectDetail | null {
  const d = (err as any)?.response?.data?.detail;
  return d && typeof d === 'object' && !Array.isArray(d) ? (d as RedirectDetail) : null;
}

/** GET a page payload; a Django-style redirect in the error turns into toast + navigate. */
export function useDocPage<T>(key: unknown[], url: string, params?: Record<string, unknown>, options?: { refetchInterval?: number }) {
  const navigate = useNavigate();
  const toast = useToast();
  const q = useQuery({
    queryKey: ['doccore', ...key, params ?? {}],
    queryFn: async () => (await api.get<T>(url, { params })).data,
    retry: false,
    refetchInterval: options?.refetchInterval,
  });
  useEffect(() => {
    const d = detailOf(q.error);
    if (d?.redirect) {
      if (d.message) (d.level === 'success' ? toast.success : d.level === 'warning' ? toast.warning : toast.error)(d.message);
      navigate(d.redirect, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.error]);
  const redirecting = !!detailOf(q.error)?.redirect;
  return { ...q, redirecting };
}

/** Handles the result of a form POST: success -> toast + navigate; errors -> field errors / toast / redirect. */
export function useSubmitHandlers() {
  const navigate = useNavigate();
  const toast = useToast();
  const onSuccess = useCallback((data: { message?: string; redirect?: string; warning?: string | null }) => {
    if (data?.warning) toast.warning(data.warning);
    if (data?.message) toast.success(data.message);
    if (data?.redirect) navigate(data.redirect);
  }, [navigate, toast]);
  const onError = useCallback((err: unknown, setErrors?: (e: Record<string, string>) => void) => {
    const d = detailOf(err);
    if (d?.errors) { setErrors?.(d.errors); return; }
    if (d?.message) toast.error(d.message);
    else toast.error(errorMessage(err));
    if (d?.redirect) navigate(d.redirect);
  }, [navigate, toast]);
  return { onSuccess, onError };
}

/* ------------------------------------------------------------------ stage labels */
type Tone = 'ok' | 'warn' | 'danger' | 'muted' | 'accent';
/** Most templates: 0 Draft / 1 Under Review / 2 Approved / 3 Needs Revision (or "Revised"). */
export function Stage({ value, revisedLabel = 'Needs Revision', tones }: { value: number | null | undefined; revisedLabel?: string; tones?: Partial<Record<number, Tone>> }) {
  const labels: Record<number, string> = { 0: 'Draft', 1: 'Under Review', 2: 'Approved', 3: revisedLabel };
  const defaultTones: Record<number, Tone> = { 0: 'muted', 1: 'warn', 2: 'ok', 3: 'danger', ...tones };
  if (value === null || value === undefined || !(value in labels)) return null;
  return <StageStatus label={labels[value]} tone={defaultTones[value]} />;
}

export function stageLabel(value: number, revisedLabel = 'Needs Revision'): string {
  return ({ 0: 'Draft', 1: 'Under Review', 2: 'Approved', 3: revisedLabel } as Record<number, string>)[value] ?? '';
}

/* ------------------------------------------------------------------ Office 365 */
/** "Document Already Open" popup used by every page with an Office 365 button. */
export function LockedPopup({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title={<span className="row-tight"><Lock size={15} /> Document Already Open</span>}
      footer={<button className="btn btn-primary" onClick={onClose}>OK, Got it</button>}>
      <div className="center stack">
        <FileText size={40} className="dc-accent" />
        <p>This document is already open in Office 365.</p>
        <p className="small muted">Please use the existing browser window to continue editing, or close it first before opening again.</p>
      </div>
    </Modal>
  );
}

/** POST /api/office365/open/:versionId (viewer module). Returns item_id on success. */
export function useOffice365() {
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const open = useCallback(async (versionId: number): Promise<string | null> => {
    setBusy(versionId);
    try {
      const { data } = await api.post(`/api/office365/open/${versionId}`, {});
      if (data?.error) {
        if (data.is_locked) setLocked(true); else window.alert(`Error: ${data.error}`);
        return null;
      }
      window.open(data.edit_url, '_blank');
      return data.item_id ?? null;
    } catch (err: any) {
      const body = err?.response?.data;
      if (body?.is_locked) setLocked(true);
      else if (body?.error) window.alert(`Error: ${body.error}`);
      else window.alert(`Failed to open in Office 365: ${errorMessage(err)}`);
      return null;
    } finally {
      setBusy(null);
    }
  }, []);
  const sync = useCallback(async (versionId: number, itemId: string | null | undefined): Promise<boolean> => {
    if (!itemId) { window.alert('No Office 365 session found. Please open the document first.'); return false; }
    if (!window.confirm('This will overwrite the local file with the version from Office 365. Continue?')) return false;
    setBusy(versionId);
    try {
      const { data } = await api.post(`/api/office365/sync/${versionId}`, { item_id: itemId });
      if (data?.error) { window.alert(`Sync error: ${data.error}`); return false; }
      window.alert('File synced back successfully!');
      return true;
    } catch (err: any) {
      const body = err?.response?.data;
      window.alert(body?.error ? `Sync error: ${body.error}` : `Sync failed: ${errorMessage(err)}`);
      return false;
    } finally {
      setBusy(null);
    }
  }, []);
  const popup = <LockedPopup open={locked} onClose={() => setLocked(false)} />;
  return { open, sync, busy, popup };
}

export function SyncIcon() { return <RefreshCw size={14} />; }

/** Django `|filesizeformat` */
export function filesizeformat(bytes: number | null | undefined): string {
  const b = bytes ?? 0;
  const KB = 1024, MB = KB * 1024, GB = MB * 1024, TB = GB * 1024;
  const fmt = (n: number) => n.toFixed(1);
  if (b < KB) return `${b} byte${b === 1 ? '' : 's'}`;
  if (b < MB) return `${fmt(b / KB)} KB`;
  if (b < GB) return `${fmt(b / MB)} MB`;
  if (b < TB) return `${fmt(b / GB)} GB`;
  return `${fmt(b / TB)} TB`;
}

export const ALLOWED_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'];
export const ACCEPT_DOCUMENTS = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx';
