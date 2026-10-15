import { useCallback, useEffect, useState, type ReactNode, type RefObject } from 'react';
import { FileText, Lock, Maximize2, Minimize2 } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Badge, Modal, Spinner } from '@/components/ui';

/** "Document Already Open" popup shown when OneDrive answers 423 (is_locked). */
export function LockedDocumentModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title={<span className="row"><Lock size={16} /> Document Already Open</span>}
      footer={<button className="btn btn-primary" onClick={onClose}>OK, Got it</button>}>
      <div className="stack center">
        <FileText size={40} className="status-accent" />
        <p>This document is already open in Office 365.</p>
        <p className="muted small">Please use the existing browser window to continue editing, or close it first before opening again.</p>
      </div>
    </Modal>
  );
}

/**
 * "Office 365" button: POST /api/viewer/office365/open/:id (or reference/open) and open the
 * returned edit URL in a new tab — same flow as the Django templates.
 */
export function Office365Button({ versionId, referenceId, label = 'Office 365', busyLabel, className = 'btn btn-secondary btn-sm' }: {
  versionId?: number; referenceId?: number; label?: ReactNode; busyLabel?: ReactNode; className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(false);
  const open = async () => {
    setBusy(true);
    const url = referenceId ? `/api/viewer/office365/reference/open/${referenceId}` : `/api/viewer/office365/open/${versionId}`;
    try {
      const { data } = await api.post(url, {});
      if (data?.error) {
        if (data.is_locked) setLocked(true); else window.alert(`Error: ${data.error}`);
        return;
      }
      window.open(data.edit_url, '_blank');
    } catch (err: any) {
      const body = err?.response?.data;
      if (body?.is_locked) setLocked(true);
      else if (body?.error) window.alert(`Error: ${body.error}`);
      else window.alert(`Failed to open in Office 365: ${errorMessage(err)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className={className} onClick={open} disabled={busy}>
        {busy ? <><Spinner />{busyLabel ? <> {busyLabel}</> : null}</> : <><FileText size={14} /> {label}</>}
      </button>
      <LockedDocumentModal open={locked} onClose={() => setLocked(false)} />
    </>
  );
}

export function StageBadge({ status }: { status: number }) {
  if (status === 0) return <Badge tone="warn">Draft</Badge>;
  if (status === 1) return <Badge tone="accent">Under Review</Badge>;
  if (status === 2) return <Badge tone="ok">Approved</Badge>;
  if (status === 3) return <Badge tone="warn">Draft Under Revision</Badge>;
  return null;
}

/** Fullscreen toggle for an element (Fullscreen API), tracking ESC exits. */
export function useFullscreen(ref: RefObject<HTMLElement>) {
  const [isFull, setFull] = useState(false);
  useEffect(() => {
    const onChange = () => setFull(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);
  const toggle = useCallback(() => {
    if (!document.fullscreenElement) {
      const el = ref.current as any;
      (el?.requestFullscreen || el?.webkitRequestFullscreen || el?.msRequestFullscreen)?.call(el);
    } else {
      const d = document as any;
      (d.exitFullscreen || d.webkitExitFullscreen || d.msExitFullscreen)?.call(d);
    }
  }, [ref]);
  return { isFull, toggle };
}

export function FullscreenButton({ isFull, onClick }: { isFull: boolean; onClick: () => void }) {
  return (
    <button type="button" className="btn btn-secondary btn-sm btn-icon" title="Toggle Fullscreen" onClick={onClick}>
      {isFull ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
    </button>
  );
}

/** Loading / error overlay drawn over the WebViewer container. */
export function ViewerOverlay({ children }: { children: ReactNode }) {
  return <div className="vw-overlay">{children}</div>;
}
