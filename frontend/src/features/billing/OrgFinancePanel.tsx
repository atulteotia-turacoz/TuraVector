/** University admin's dashboard: what Turacoz has invoiced, what is paid and outstanding, with a link to the reports. */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { Panel } from '@/components/ui';
import { inr } from './api';
import './billing.css';

interface Analytics {
  trend: { month: string; billed: number; received: number }[];
  ageing: { amount: number }[];
  tax: { cgst: number; sgst: number; igst: number };
  totals: { billed: number; received: number };
}
const MONTHS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

export function OrgFinancePanel() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ['invoices', 'analytics', true], enabled: !!user?.is_org_admin,
    queryFn: async () => (await api.get<Analytics>('/api/org/finance/analytics')).data });
  if (!user?.is_org_admin || !q.data) return null;
  const a = q.data;
  const year = a.trend.reduce((t, m) => t + m.billed, 0);
  const outstanding = a.ageing.reduce((t, b) => t + b.amount, 0);
  const max = Math.max(1, ...a.trend.map((m) => Math.max(m.billed, m.received)));
  return (
    <Panel title="Finance" flush actions={<Link className="btn btn-ghost btn-sm" to="/content-lab-management/finance/reports/"><BarChart3 size={13} /> Finance reports</Link>}>
      <div className="of-tiles">
        <div><span className="of-num">{inr(year)}</span><span className="of-label">Invoiced, last 12 months</span></div>
        <div><span className="of-num">{inr(a.totals.received)}</span><span className="of-label">Paid</span></div>
        <div><span className="of-num" style={outstanding ? { color: 'var(--danger)' } : undefined}>{inr(outstanding)}</span><span className="of-label">Outstanding</span></div>
        <div><span className="of-num">{inr(a.tax.cgst + a.tax.sgst + a.tax.igst)}</span><span className="of-label">GST on invoices</span></div>
      </div>
      <div className="of-chart" role="img" aria-label="Invoiced and paid per month">
        {a.trend.map((m) => {
          const mo = Number(m.month.split('-')[1]);
          return (
            <div key={m.month} className="of-col" title={`${m.month}: invoiced ${inr(m.billed)} · paid ${inr(m.received)}`}>
              <div className="of-track">
                <span className="fa-bar fa-billed" style={{ height: `${(m.billed / max) * 100}%` }} />
                <span className="fa-bar fa-received" style={{ height: `${(m.received / max) * 100}%` }} />
              </div>
              <span className="fa-label">{MONTHS[mo - 1]}</span>
            </div>
          );
        })}
      </div>
      <div className="of-key small muted">
        <span><span className="md-swatch" style={{ background: 'var(--accent)' }} /> Invoiced</span>
        <span><span className="md-swatch" style={{ background: 'var(--c3)' }} /> Paid</span>
      </div>
    </Panel>
  );
}
