/** Finance analytics on the Finance Dashboard: billed vs received, ageing, clients, services, cycle times, GST. */
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Loading, Panel } from '@/components/ui';
import { money as inr } from '@/pages/RateCards';

interface Analytics {
  trend: { month: string; billed: number; received: number; invoices: number }[];
  by_organisation: { id: number; name: string; billed: number; received: number; outstanding: number; invoices: number }[];
  by_service: { name: string; amount: number; quantity: number; lines: number }[];
  ageing: { label: string; amount: number; count: number }[];
  tax: { cgst: number; sgst: number; igst: number; taxable: number };
  cycle_days: { turacoz_approval: number | null; client_approval: number | null; payment: number | null };
  totals: { billed: number; received: number; collection_rate: number | null };
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const short = (v: number) => (v >= 1e7 ? `₹${(v / 1e7).toFixed(1)}Cr` : v >= 1e5 ? `₹${(v / 1e5).toFixed(1)}L` : v >= 1e3 ? `₹${(v / 1e3).toFixed(1)}k` : `₹${Math.round(v)}`);

function HBars({ rows, empty }: { rows: { label: string; value: number; note?: string }[]; empty: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length || rows.every((r) => !r.value)) return <div className="panel-body small muted">{empty}</div>;
  return (
    <ul className="md-hbars">
      {rows.map((r) => (
        <li key={r.label} title={`${r.label}: ${inr(r.value)}${r.note ? ` · ${r.note}` : ''}`}>
          <span className="md-hbar-label truncate">{r.label}</span>
          <span className="md-hbar-track"><span className="md-hbar-fill" style={{ width: `${(r.value / max) * 100}%` }} /></span>
          <span className="md-hbar-value tnum fa-val"><strong>{short(r.value)}</strong></span>
        </li>
      ))}
    </ul>
  );
}

export function FinanceAnalytics() {
  const q = useQuery({ queryKey: ['admin', 'invoices', 'analytics'], queryFn: async () => (await api.get<Analytics>('/api/billing/analytics')).data });
  if (q.isLoading) return <Loading />;
  if (!q.data) return null;
  const a = q.data;
  const max = Math.max(1, ...a.trend.map((m) => Math.max(m.billed, m.received)));
  const days = (v: number | null) => (v === null ? '—' : `${v}`);
  return (
    <div className="stack-lg fa">
            <Panel title="Billed and received — last 12 months"
        actions={<div className="md-chart-key small muted">
          <span><span className="md-swatch" style={{ background: 'var(--accent)' }} /> Billed {inr(a.totals.billed)}</span>
          <span><span className="md-swatch" style={{ background: 'var(--c3)' }} /> Received {inr(a.totals.received)}</span>
        </div>}>
        <div className="fa-chart" role="img" aria-label="Billed and received per month for the last 12 months">
          {a.trend.map((m) => {
            const [y, mo] = m.month.split('-').map(Number);
            return (
              <div key={m.month} className="fa-col" title={`${MONTHS[mo - 1]} ${y}: billed ${inr(m.billed)} (${m.invoices} invoices) · received ${inr(m.received)}`}>
                <span className="fa-v tnum">{m.billed ? short(m.billed) : ''}</span>
                <div className="fa-track">
                  <span className="fa-bar fa-billed" style={{ height: `${(m.billed / max) * 100}%` }} />
                  <span className="fa-bar fa-received" style={{ height: `${(m.received / max) * 100}%` }} />
                </div>
                <span className="fa-label">{MONTHS[mo - 1]}</span>
              </div>
            );
          })}
        </div>
      </Panel>

      <div className="md-tiles fa-tiles panel">
        <div><div className="stat-value tnum">{a.totals.collection_rate === null ? '—' : `${a.totals.collection_rate}%`}</div><div className="stat-label">Collected</div><div className="stat-note">of everything billed</div></div>
        <div><div className="stat-value tnum">{days(a.cycle_days.turacoz_approval)}<span className="md-unit"> days</span></div><div className="stat-label">Turacoz approval</div><div className="stat-note">average</div></div>
        <div><div className="stat-value tnum">{days(a.cycle_days.client_approval)}<span className="md-unit"> days</span></div><div className="stat-label">Client approval</div><div className="stat-note">average</div></div>
        <div><div className="stat-value tnum">{days(a.cycle_days.payment)}<span className="md-unit"> days</span></div><div className="stat-label">Approval to payment</div><div className="stat-note">average</div></div>
        <div><div className="stat-value tnum">{short(a.tax.cgst + a.tax.sgst + a.tax.igst)}</div><div className="stat-label">GST billed</div>
          <div className="stat-note">CGST {short(a.tax.cgst)} · SGST {short(a.tax.sgst)} · IGST {short(a.tax.igst)}</div></div>
      </div>

      <div className="grid-2 fa-grid">
        <Panel title="Outstanding by age" flush>
          <HBars empty="Nothing outstanding." rows={a.ageing.map((b) => ({ label: b.label, value: b.amount, note: `${b.count} invoice${b.count === 1 ? '' : 's'}` }))} />
        </Panel>
        <Panel title="Top clients by billing" flush>
          <HBars empty="Nothing billed yet." rows={a.by_organisation.map((o) => ({ label: o.name, value: o.billed, note: `received ${inr(o.received)}, outstanding ${inr(o.outstanding)}` }))} />
        </Panel>
        <Panel title="Revenue by service" flush>
          <HBars empty="Nothing billed yet." rows={a.by_service.map((s) => ({ label: s.name, value: s.amount, note: `${s.lines} line${s.lines === 1 ? '' : 's'}` }))} />
        </Panel>
      </div>
    </div>
  );
}
