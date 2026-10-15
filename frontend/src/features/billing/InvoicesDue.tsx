/** Dashboard panel for a university admin: invoices waiting for their approval or payment. */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { Badge, Panel } from '@/components/ui';
import { STATUS_TONE, inr, type InvoiceRow } from './api';
import './billing.css';

export function InvoicesDue() {
  const { user } = useAuth();
  const q = useQuery({
    queryKey: ['invoices', false, 'due'],
    queryFn: async () => (await api.get<{ invoices: InvoiceRow[]; outstanding: number }>('/api/org/invoices')).data,
    enabled: !!user?.is_org_admin,
  });
  if (!user?.is_org_admin || !q.data) return null;
  const due = q.data.invoices.filter((i) => i.status === 'pending_client' || i.status === 'awaiting_payment');
  return (
    <Panel title="Invoices" flush actions={<Link className="act small" to="/content-lab-management/invoices/">View all</Link>}>
      {due.length === 0 ? (
        <div className="panel-body small muted">Nothing to approve or pay.</div>
      ) : (
        <div className="inv-due">
          <div className="panel-body small" style={{ paddingBottom: 10 }}>
            <strong>{inr(q.data.outstanding)}</strong> <span className="muted">outstanding · {due.length} invoice{due.length === 1 ? '' : 's'} need you</span>
          </div>
          {due.slice(0, 5).map((i) => (
            <Link key={i.id} to={`/content-lab-management/invoices/${i.id}/`}>
              <span><span className="mono">{i.number}</span><span className="tiny faint" style={{ display: 'block' }}>{inr(i.total)}</span></span>
              <Badge tone={STATUS_TONE[i.status]}>{i.status === 'pending_client' ? 'Approve' : 'Pay'}</Badge>
            </Link>
          ))}
        </div>
      )}
    </Panel>
  );
}
