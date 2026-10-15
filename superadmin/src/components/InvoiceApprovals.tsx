/** Superadmin dashboard: a one-line highlight when invoices wait for Turacoz approval or are overdue. */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, ReceiptText } from 'lucide-react';
import { api } from '@/lib/api';
import { money } from '@/pages/RateCards';

type Stage = 'pending_turacoz' | 'pending_client' | 'awaiting_payment';
interface Summary { counts: Record<Stage, { count: number; amount: number; overdue: number }>; threshold_days: number }

export function InvoiceApprovals() {
  const q = useQuery({ queryKey: ['admin', 'invoices', 'summary'], queryFn: async () => (await api.get<Summary>('/api/billing/summary')).data, refetchInterval: 60000 });
  if (!q.data) return null;
  const { counts, threshold_days: days } = q.data;
  const toApprove = counts.pending_turacoz.count;
  const overdue = counts.pending_turacoz.overdue + counts.pending_client.overdue + counts.awaiting_payment.overdue;
  if (!toApprove && !overdue) return null;  // nothing needs attention: no banner
  return (
    <Link to="/invoices/?view=list" className={`ap-strip ${overdue ? 'is-late' : ''}`}>
      {overdue ? <AlertTriangle size={16} /> : <ReceiptText size={16} />}
      <span className="grow">
        {toApprove > 0 && <><strong>{toApprove} invoice{toApprove === 1 ? '' : 's'}</strong> waiting for Turacoz approval · {money(counts.pending_turacoz.amount)}</>}
        {toApprove > 0 && overdue > 0 && ' · '}
        {overdue > 0 && <strong className="ap-late">{overdue} overdue (over {days} days)</strong>}
      </span>
      <span className="ap-go">Review now <ArrowRight size={14} /></span>
    </Link>
  );
}
