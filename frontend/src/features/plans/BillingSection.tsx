/** Plans page: who plan invoices are made out to, and the workspace's invoices and payment receipts. */
import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, ReceiptText, Save } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Field, Loading, Spinner, useToast } from '@/components/ui';
import { INDIAN_STATES, money } from './shared';

export interface BillingDetails {
  legal_name: string; address: string; state: string; state_code: string; country: string; gstin: string;
  billing_email: string; missing: string[];
}
interface InvoiceRow {
  id: number; number: string; plan_name: string; status: string; status_label: string; currency: string;
  subtotal: number; tax: number; total: number; created_at: string; paid_at: string | null; payment_id: string;
}

export const BILLING_KEY = ['subscriptions', 'billing'];

export default function BillingSection({ workspaceName }: { workspaceName: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: BILLING_KEY,
    queryFn: async () => (await api.get<{ details: BillingDetails; invoices: InvoiceRow[] }>('/api/subscriptions/billing')).data,
  });
  const [f, setF] = useState<BillingDetails | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (q.data) setF(q.data.details); }, [q.data]);

  if (q.isLoading || !f) return <section className="pl-section"><Loading /></section>;
  if (q.isError || !q.data) return <section className="pl-section"><ErrorNotice error={q.error} /></section>;

  const india = f.country.trim().toLowerCase() === 'india';
  const set = (k: keyof BillingDetails) => (e: { target: { value: string } }) => setF((x) => x && ({ ...x, [k]: e.target.value }));
  const pickState = (code: string) => {
    const st = INDIAN_STATES.find(([c]) => c === code);
    setF((x) => x && ({ ...x, state_code: code, state: st ? st[1] : '' }));
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.put('/api/subscriptions/billing', f);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: BILLING_KEY });
      void qc.invalidateQueries({ queryKey: ['subscriptions', 'overview'] });
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };

  return (
    <>
      <section className="pl-section" id="billing-details">
        <h2>Billing details</h2>
        <form className="pl-box" onSubmit={save}>
          <p className="small muted" style={{ marginTop: 0 }}>
            Invoices are made out to these details. GST is added to plan prices: CGST + SGST within the same state as
            Turacoz, IGST from other states.
          </p>
          <div className="form-grid">
            <Field label="Name on invoice"><input className="input" maxLength={200} value={f.legal_name} placeholder={workspaceName} onChange={set('legal_name')} /></Field>
            <Field label="Billing email"><input className="input" type="email" maxLength={200} value={f.billing_email} onChange={set('billing_email')} /></Field>
            <div className="span-2"><Field label="Address"><input className="input" maxLength={500} value={f.address} onChange={set('address')} /></Field></div>
            <Field label="Country" required><input className="input" required maxLength={100} value={f.country} onChange={set('country')} /></Field>
            {india ? (
              <Field label="State" required>
                <select className="input" required value={INDIAN_STATES.some(([c]) => c === f.state_code) ? f.state_code : ''} onChange={(e) => pickState(e.target.value)}>
                  <option value="">Choose your state</option>
                  {INDIAN_STATES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
                </select>
              </Field>
            ) : (
              <Field label="State / region"><input className="input" maxLength={100} value={f.state} onChange={set('state')} /></Field>
            )}
            <Field label="GSTIN" help="Optional — add it to claim input tax credit.">
              <input className="input" maxLength={20} value={f.gstin} onChange={set('gstin')} style={{ textTransform: 'uppercase' }} />
            </Field>
          </div>
          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn btn-primary btn-sm" disabled={busy}>{busy ? <Spinner /> : <Save size={14} />} Save details</button>
          </div>
        </form>
      </section>

      <section className="pl-section">
        <h2>Invoices &amp; receipts</h2>
        {q.data.invoices.length === 0 ? (
          <div className="pl-sub"><span className="muted small">No invoices yet. An invoice and a payment receipt appear here after each plan payment.</span></div>
        ) : (
          <div className="table-wrap pl-box" style={{ padding: 0 }}>
            <table className="tbl">
              <thead><tr><th>Invoice</th><th>Plan</th><th>Date</th><th className="num">Amount</th><th>Status</th><th /></tr></thead>
              <tbody>
                {q.data.invoices.map((inv) => (
                  <tr key={inv.id}>
                    <td className="nowrap"><strong>{inv.number}</strong></td>
                    <td className="small">{inv.plan_name}</td>
                    <td className="small nowrap">{formatDate(inv.paid_at || inv.created_at)}</td>
                    <td className="num nowrap">{money(inv.total, inv.currency)}
                      {inv.tax > 0 && <span className="tiny faint" style={{ display: 'block' }}>incl. {money(inv.tax, inv.currency)} GST</span>}</td>
                    <td><span className={`badge ${inv.status === 'paid' ? 'badge-ok' : ''}`}>{inv.status_label}</span></td>
                    <td><div className="row-tight nowrap">
                      <Link className="btn btn-ghost btn-sm" to={`/plans/invoices/${inv.id}/`}><FileText size={14} /> Invoice</Link>
                      <Link className="btn btn-ghost btn-sm" to={`/plans/invoices/${inv.id}/?doc=receipt`}><ReceiptText size={14} /> Receipt</Link>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
