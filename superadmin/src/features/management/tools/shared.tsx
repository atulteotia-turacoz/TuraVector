import { useState } from 'react';
import type { AxiosError } from 'axios';
import { api } from '@/lib/api';
import { useConfirm, useToast } from '@/components/ui';

/** Status badge used by mail_logs.html / email_log_detail.html. */
export function StatusBadge({ status, display, long }: { status: string; display: string; long?: boolean }) {
  if (status === 'sent') return <span className="badge badge-ok">{long ? 'Sent Successfully' : 'Sent'}</span>;
  if (status === 'failed') return <span className="badge badge-danger">Failed</span>;
  if (status === 'pending') return <span className="badge badge-warn">Pending</span>;
  return <span className="badge">{display}</span>;
}

/** retryEmail(id) from the mail log templates: confirm, POST, toast, refresh on success after 1.5 s. */
export function useRetryEmail(onDone: () => void) {
  const confirm = useConfirm();
  const toast = useToast();
  const [retrying, setRetrying] = useState<number | null>(null);
  const retry = async (id: number) => {
    if (!(await confirm({ title: 'Retry email', message: 'Are you sure you want to retry sending this email?', confirmLabel: 'Retry' }))) return;
    setRetrying(id);
    try {
      const { data } = await api.post(`/api/tools/mail-logs/${id}/retry`);
      if (data.status === 'sent') {
        toast.success('Email retried successfully!');
        setTimeout(onDone, 1500);
      } else {
        toast.error(`Failed to retry email: ${data.error || data.message}`);
      }
    } catch (err) {
      const d = (err as AxiosError<any>).response?.data;
      if (d && (d.error || d.message)) toast.error(`Failed to retry email: ${d.error || d.message}`);
      else toast.error('Failed to retry email');
    } finally {
      setRetrying(null);
    }
  };
  return { retry, retrying };
}
