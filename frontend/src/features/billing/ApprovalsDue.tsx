/** Turacoz approver's dashboard: a one-line highlight when invoices wait for approval or are overdue. */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, ReceiptText } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { inr } from './api';
import './billing.css';

type Stage = 'pending_turacoz' | 'pending_client' | 'awaiting_payment';
interface Summary { counts: Record<Stage, { count: number; amount: number; overdue: number }>; threshold_days: number }

export function ApprovalsDue() {
  const { user } = useAuth();
  const q = useQuery({
    queryKey: ['invoices', 'summary'],
    queryFn: async () => (await api.get<Summary>('/api/billing/summary')).data,
    enabled: !!user?.is_invoice_approver, refetchInterval: 60000,
  });
  if (!user?.is_invoice_approver || !q.data) return null;
  const { counts, threshold_days: days } = q.data;
  const toApprove = counts.pending_turacoz.count;
  const overdue = counts.pending_turacoz.overdue + counts.pending_client.overdue + counts.awaiting_payment.overdue;
  if (!toApprove && !overdue) return null;  // nothing needs attention: no banner
  return (
    <Link to="/content-lab-management/invoices/" className={`ap-strip ${overdue ? 'is-late' : ''}`}>
      {overdue ? <AlertTriangle size={16} /> : <ReceiptText size={16} />}
      <span className="grow">
        {toApprove > 0 && <><strong>{toApprove} invoice{toApprove === 1 ? '' : 's'}</strong> waiting for your approval · {inr(counts.pending_turacoz.amount)}</>}
        {toApprove > 0 && overdue > 0 && ' · '}
        {overdue > 0 && <strong className="ap-late">{overdue} overdue (over {days} days)</strong>}
      </span>
      <span className="ap-go">Review now <ArrowRight size={14} /></span>
    </Link>
  );
}
