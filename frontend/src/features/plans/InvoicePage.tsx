/** A plan invoice, shown as the GST tax invoice or as the payment receipt, ready to print or save as PDF. */
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Printer } from 'lucide-react';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Loading } from '@/components/ui';
import { NotificationBell, UserMenu } from '@/layouts/AppShell';
import { ThemePicker } from '@/components/ThemePicker';
import { BareFrame } from '@/features/auth/components';
import { money } from './shared';

interface Party {
  company_name?: string; name?: string; address: string; state: string; state_code: string; country: string;
  gstin: string; pan?: string; email: string; phone?: string;
}
interface InvoiceDoc {
  id: number; number: string; status: string; status_label: string; currency: string; period_start: string | null;
  period_end: string | null; created_at: string; paid_at: string | null; payment_id: string; gateway: string;
  tax_mode: string; tax_mode_label: string; subtotal: number; cgst: number; sgst: number; igst: number; total: number;
  amount_in_words: string; seller: Party; buyer: Party;
  lines: { id: number; description: string; sac_code: string; quantity: number; rate: number; amount: number; tax_percent: number }[];
}

function PartyBlock({ title, p }: { title: string; p: Party }) {
  return (
    <div className="pl-doc-party">
      <div className="pl-doc-label">{title}</div>
      <strong>{p.company_name || p.name}</strong>
      {p.address && <div>{p.address}</div>}
      {(p.state || p.country) && <div>{[p.state, p.country].filter(Boolean).join(', ')}{p.state_code ? ` (State code ${p.state_code})` : ''}</div>}
      {p.gstin && <div>GSTIN: {p.gstin}</div>}
      {p.pan && <div>PAN: {p.pan}</div>}
      {p.email && <div>{p.email}</div>}
    </div>
  );
}

export default function InvoicePage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const receipt = params.get('doc') === 'receipt';
  const q = useQuery({
    queryKey: ['subscriptions', 'invoice', id],
    queryFn: async () => (await api.get<InvoiceDoc>(`/api/subscriptions/invoices/${id}`)).data,
  });
  const right = <><ThemePicker /><NotificationBell /><UserMenu profilePath="/profile/" /></>;
  const show = (doc: 'invoice' | 'receipt') => setParams(doc === 'receipt' ? { doc } : {}, { replace: true });

  if (q.isLoading) return <BareFrame right={right} theme={false}><Loading /></BareFrame>;
  if (q.isError || !q.data) return <BareFrame right={right} theme={false}><div className="pl-page"><ErrorNotice error={q.error} /></div></BareFrame>;
  const inv = q.data;
  const tax = inv.cgst + inv.sgst + inv.igst;
  const cur = inv.currency;

  return (
    <BareFrame right={right} theme={false}>
      <div className="pl-page pl-doc-page">
        <div className="row no-print" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <Link to="/plans/" className="row-tight small muted"><ArrowLeft size={14} /> Back to plans &amp; billing</Link>
          <div className="row-tight">
            <div className="filter-tabs">
              <button type="button" className={`filter-tab ${!receipt ? 'active' : ''}`} onClick={() => show('invoice')}>Tax invoice</button>
              <button type="button" className={`filter-tab ${receipt ? 'active' : ''}`} onClick={() => show('receipt')}>Payment receipt</button>
            </div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => window.print()}><Printer size={14} /> Print / Save PDF</button>
          </div>
        </div>

        <article className="pl-doc">
          <header className="pl-doc-head">
            <div>
              <h1>{receipt ? 'Payment receipt' : 'Tax invoice'}</h1>
              <div className="small muted">{inv.seller.company_name}</div>
            </div>
            <dl className="pl-doc-meta">
              <dt>{receipt ? 'Receipt no.' : 'Invoice no.'}</dt><dd>{receipt ? `R-${inv.number}` : inv.number}</dd>
              {receipt && <><dt>Against invoice</dt><dd>{inv.number}</dd></>}
              <dt>{receipt ? 'Payment date' : 'Invoice date'}</dt><dd>{formatDate(receipt ? (inv.paid_at || inv.created_at) : inv.created_at)}</dd>
              <dt>Status</dt><dd>{inv.status_label}</dd>
            </dl>
          </header>

          <div className="pl-doc-parties">
            <PartyBlock title={receipt ? 'Received by' : 'From'} p={inv.seller} />
            <PartyBlock title={receipt ? 'Received from' : 'Bill to'} p={inv.buyer} />
          </div>

          {receipt ? (
            <>
              <table className="pl-doc-table">
                <tbody>
                  <tr><th>Amount received</th><td className="num"><strong>{money(inv.total, cur)}</strong></td></tr>
                  <tr><th>Amount in words</th><td>{inv.amount_in_words}</td></tr>
                  <tr><th>For</th><td>{inv.lines.map((l) => l.description).join('; ')}</td></tr>
                  <tr><th>Payment method</th><td>{inv.gateway === 'razorpay' ? 'Online (Razorpay)' : 'Recorded by Turacoz'}</td></tr>
                  <tr><th>Payment reference</th><td>{inv.payment_id || '—'}</td></tr>
                </tbody>
              </table>
              <p className="small muted">This receipt confirms payment of the tax invoice {inv.number}.</p>
            </>
          ) : (
            <>
              <div className="table-wrap">
                <table className="pl-doc-table">
                  <thead><tr><th>Description</th><th>SAC</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amount</th></tr></thead>
                  <tbody>
                    {inv.lines.map((l) => (
                      <tr key={l.id}><td>{l.description}</td><td>{l.sac_code || '—'}</td><td className="num">{l.quantity}</td>
                        <td className="num">{money(l.rate, cur)}</td><td className="num">{money(l.amount, cur)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="pl-doc-totals">
                <div><span>Taxable value</span><span>{money(inv.subtotal, cur)}</span></div>
                {inv.cgst > 0 && <div><span>CGST @ {inv.lines[0]?.tax_percent / 2}%</span><span>{money(inv.cgst, cur)}</span></div>}
                {inv.sgst > 0 && <div><span>SGST @ {inv.lines[0]?.tax_percent / 2}%</span><span>{money(inv.sgst, cur)}</span></div>}
                {inv.igst > 0 && <div><span>IGST @ {inv.lines[0]?.tax_percent}%</span><span>{money(inv.igst, cur)}</span></div>}
                {tax === 0 && <div><span>GST</span><span>{money(0, cur)}</span></div>}
                <div className="pl-doc-total"><span>Total</span><span>{money(inv.total, cur)}</span></div>
              </div>
              <p className="small"><strong>Amount in words:</strong> {inv.amount_in_words}</p>
              <p className="small muted">
                {inv.tax_mode_label}. Paid {inv.paid_at ? `on ${formatDate(inv.paid_at)}` : ''}{inv.payment_id ? ` · payment reference ${inv.payment_id}` : ''}.
              </p>
            </>
          )}
          <p className="tiny faint" style={{ marginBottom: 0 }}>This is a computer-generated document and needs no signature.</p>
        </article>
      </div>
    </BareFrame>
  );
}
