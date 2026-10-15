/** Invoices list — a university admin's own invoices, or the Turacoz approval queue. */
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { Badge, Empty, ErrorNotice, Loading, PageHeader, Panel, Stat, Tabs, useToast } from '@/components/ui';
import { STATUS_TONE, inr, invoiceBase, type InvoiceRow, type InvoiceStatus } from './api';
import './billing.css';

interface Waiting { organisation_id: number; organisation: string; requests: number; since: string | null; billing_cycle: string; missing: string[] }
interface Listing { invoices: InvoiceRow[]; counts: Partial<Record<InvoiceStatus, number>>; outstanding?: number; waiting?: Waiting[] }

export default function InvoicesPage() {
  const { user } = useAuth();
  const approver = !!user?.is_invoice_approver;
  const allowed = approver || !!user?.is_org_admin;
  const [params, setParams] = useSearchParams();
  const organisation = approver ? params.get('organisation') ?? '' : '';
  const [status, setStatus] = useState<'' | InvoiceStatus>(approver && !organisation ? 'pending_turacoz' : '');
  const q = useQuery({
    queryKey: ['invoices', approver, status, organisation],
    queryFn: async () => (await api.get<Listing>(invoiceBase(approver), { params: { status, organisation: organisation || undefined } })).data,
    enabled: allowed, placeholderData: (prev) => prev,
  });
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();

  if (!allowed) return <Empty title="Invoices">Invoices are available to your institution's administrator.</Empty>;
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { invoices, counts } = q.data;
  const n = (s: InvoiceStatus) => counts[s] ?? 0;

  const generate = async (w: Waiting) => {
    try {
      const { data } = await api.post(`/api/billing/organisations/${w.organisation_id}/generate`, {});
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['invoices'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };

  const tabs: { value: '' | InvoiceStatus; label: string }[] = approver
    ? [{ value: 'pending_turacoz', label: `To approve (${n('pending_turacoz')})` },
       { value: 'pending_client', label: `With client (${n('pending_client')})` },
       { value: 'awaiting_payment', label: `Awaiting payment (${n('awaiting_payment')})` },
       { value: 'paid', label: `Paid (${n('paid')})` }, { value: 'rejected', label: 'Cancelled' }, { value: '', label: 'All' }]
    : [{ value: '', label: 'All' }, { value: 'pending_client', label: `Needs your approval (${n('pending_client')})` },
       { value: 'awaiting_payment', label: `To pay (${n('awaiting_payment')})` }, { value: 'paid', label: `Paid (${n('paid')})` }];

  return (
    <>
      <PageHeader eyebrow={approver ? 'Turacoz' : user?.organisation?.name} title="Invoices"
        subtitle={approver ? 'Check the invoices generated from service requests, adjust them if needed and send them to the client.'
          : 'Invoices for the services your members requested. Approve them, then pay online.'} />
      {!approver && (
        <div className="stat-grid" style={{ marginBottom: 20 }}>
          <Stat value={n('pending_client')} label="Waiting for your approval" />
          <Stat value={n('awaiting_payment')} label="Approved, to pay" />
          <Stat value={inr(q.data.outstanding ?? 0)} label="Outstanding" />
          <Stat value={n('paid')} label="Paid" />
        </div>
      )}
      {approver && !!q.data.waiting?.length && (
        <Panel title="Requests not invoiced yet" flush>
          <table className="tbl">
            <thead><tr><th>University / organisation</th><th className="num">Requests</th><th>Since</th><th>Billing</th><th /></tr></thead>
            <tbody>
              {q.data.waiting.map((w) => (
                <tr key={w.organisation_id}>
                  <td><strong>{w.organisation}</strong></td>
                  <td className="num">{w.requests}</td>
                  <td className="small">{w.since ? formatDate(w.since) : ''}</td>
                  <td className="small">{w.missing.length ? <Badge tone="danger">Billing profile incomplete</Badge> : w.billing_cycle === 'monthly' ? 'Monthly' : 'Per submission'}</td>
                  <td className="num">{w.missing.length
                    ? <span className="tiny faint">Superadmin: complete the billing profile</span>
                    : <button className="btn btn-secondary btn-sm" onClick={() => generate(w)}>Generate invoice</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
      {organisation && (
        <div className="row-tight" style={{ marginTop: 16 }}>
          <span className="small muted">Showing {invoices[0]?.organisation ?? 'one university'} only</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setParams({})}>Show all</button>
        </div>
      )}
      <div className="inv-tabs"><Tabs value={status} onChange={setStatus} tabs={tabs} /></div>
      <section className="panel">
        {invoices.length === 0 ? <div className="panel-body muted">No invoices here.</div> : (
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th>Invoice</th>{approver && <th>Client</th>}<th>Date</th><th>Billing</th><th className="num">Total</th><th>Status</th></tr></thead>
              <tbody>
                {invoices.map((i) => (
                  <tr key={i.id} className="clickable" onClick={() => navigate(`/content-lab-management/invoices/${i.id}/`)}>
                    <td><Link className="act mono" to={`/content-lab-management/invoices/${i.id}/`} onClick={(e) => e.stopPropagation()}>{i.number}</Link></td>
                    {approver && <td>{i.organisation}</td>}
                    <td className="small nowrap">{i.created_at ? formatDate(i.created_at) : ''}</td>
                    <td className="small">{i.cycle === 'monthly' && i.period_start ? `Monthly · ${formatDate(i.period_start).replace(/^\d+ /, '')}` : i.cycle_label}</td>
                    <td className="num"><strong>{inr(i.total)}</strong></td>
                    <td><Badge tone={STATUS_TONE[i.status]}>{approver && i.status === 'pending_client' ? 'With client' : i.status_label}</Badge></td>
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
