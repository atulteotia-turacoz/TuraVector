/** Finance dashboard for a Turacoz Financial Manager: their universities / organisations and the invoice position. */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { BarChart3, FileText, Settings2 } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { Badge, Empty, ErrorNotice, Field, Loading, Modal, PageHeader, Spinner, Stat, useToast } from '@/components/ui';
import { ApprovalsDue } from './ApprovalsDue';
import { FinanceAnalytics } from './FinanceAnalytics';
import { inr } from './api';
import './billing.css';

interface OrgRow {
  id: number; name: string; kind: string; assigned: boolean; billing_cycle: string; profile_missing: string[];
  unbilled_requests: number; open: number; outstanding: number; overdue: number; to_approve: number; paid: number;
  last_invoice_at: string | null;
}
interface Dash {
  scope: 'all' | 'assigned' | 'default'; threshold_days: number; organisations: OrgRow[];
  totals: { to_approve: number; to_approve_amount: number; with_client: number; awaiting_payment: number; outstanding: number;
    paid_this_month: number; invoiced_this_month: number; overdue: number };
}

export default function FinanceDashboard() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ['invoices', 'finance-dashboard'], queryFn: async () => (await api.get<Dash>('/api/billing/dashboard')).data,
    enabled: !!user?.is_invoice_approver });
  const [edit, setEdit] = useState<OrgRow | null>(null);
  const toast = useToast();
  const qc = useQueryClient();

  if (!user?.is_invoice_approver) return <Empty title="Finance">This dashboard is for Turacoz Financial Managers.</Empty>;
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { totals: t, organisations: orgs } = q.data;
  const generate = async (o: OrgRow) => {
    try {
      const { data } = await api.post(`/api/billing/organisations/${o.id}/generate`, {});
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['invoices'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };

  return (
    <>
      <PageHeader eyebrow="Turacoz" title="Finance Dashboard"
        subtitle={q.data.scope === 'assigned' ? 'The universities and organisations you are the Financial Manager for.'
          : q.data.scope === 'default' ? 'Universities you are assigned to, and every one without its own Financial Manager.'
          : 'Every university and organisation.'}
        actions={<div className="row-tight">
          <Link className="btn btn-secondary" to="/content-lab-management/finance/reports/"><BarChart3 size={14} /> Finance reports</Link>
          <Link className="btn btn-primary" to="/content-lab-management/invoices/"><FileText size={14} /> Invoices</Link>
        </div>} />
      <ApprovalsDue />
      <div className="stat-grid" style={{ marginBottom: 20 }}>
        <Stat value={t.to_approve} label="To approve" note={inr(t.to_approve_amount)} />
        <Stat value={t.with_client} label="With clients" note="Waiting for their approval" />
        <Stat value={inr(t.outstanding)} label="Outstanding" note={`${t.awaiting_payment} approved, unpaid`} />
        <Stat value={inr(t.paid_this_month)} label="Received this month" note={`${inr(t.invoiced_this_month)} invoiced`} />
        <Stat value={t.overdue} label="Overdue" note={`Waiting over ${q.data.threshold_days} days`} />
      </div>
      <section className="panel">
        <div className="panel-head"><h2>Universities &amp; organisations ({orgs.length})</h2></div>
        {orgs.length === 0 ? <div className="panel-body muted">No universities or organisations are assigned to you yet.</div> : (
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th>Name</th><th>Billing</th><th className="num">To approve</th><th className="num">Open</th>
                <th className="num">Outstanding</th><th className="num">Paid</th><th>Last invoice</th><th /></tr></thead>
              <tbody>
                {orgs.map((o) => (
                  <tr key={o.id}>
                    <td><Link className="act" to={`/content-lab-management/invoices/?organisation=${o.id}`}><strong>{o.name}</strong></Link>
                      <div className="tiny faint">{o.assigned ? 'You are its Financial Manager' : 'Default Financial Manager'}</div></td>
                    <td className="small">
                      {o.profile_missing.length ? <Badge tone="danger">Profile incomplete</Badge> : o.billing_cycle === 'monthly' ? 'Monthly' : 'Per submission'}
                      {o.unbilled_requests > 0 && <div className="tiny faint">{o.unbilled_requests} request{o.unbilled_requests === 1 ? '' : 's'} not invoiced</div>}
                    </td>
                    <td className="num">{o.to_approve ? <Badge tone="warn">{o.to_approve}</Badge> : <span className="faint">0</span>}</td>
                    <td className="num">{o.open}{o.overdue > 0 && <div className="tiny" style={{ color: 'var(--danger)' }}>{o.overdue} overdue</div>}</td>
                    <td className="num">{inr(o.outstanding)}</td>
                    <td className="num">{inr(o.paid)}</td>
                    <td className="small nowrap">{o.last_invoice_at ? formatDate(o.last_invoice_at) : '—'}</td>
                    <td className="num"><div className="row-tight" style={{ justifyContent: 'flex-end' }}>
                      {o.unbilled_requests > 0 && !o.profile_missing.length && <button className="btn btn-secondary btn-sm" onClick={() => generate(o)}>Generate invoice</button>}
                      <button className="btn btn-ghost btn-sm" onClick={() => setEdit(o)}><Settings2 size={13} /> Billing</button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <FinanceAnalytics />
      {edit && <BillingModal org={edit} onClose={() => setEdit(null)} />}
    </>
  );
}

interface Profile {
  legal_name: string; address: string; state: string; state_code: string; country: string; gstin: string; billing_email: string;
  billing_cycle: string; reminder_mode: string; reminder_after_days: number | null; reminder_repeat_days: number | null; reminder_max: number | null;
  missing: string[]; financial_managers?: { uses_default: boolean; people: { id: number; name: string }[] };
}

function BillingModal({ org, onClose }: { org: OrgRow; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['invoices', 'profile', org.id], queryFn: async () => (await api.get<Profile>(`/api/billing/organisations/${org.id}/profile`)).data });
  const [form, setForm] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);
  const f = form ?? q.data;
  const set = (k: keyof Profile) => (e: { target: { value: string } }) => setForm({ ...(f as Profile), [k]: e.target.value });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.put(`/api/billing/organisations/${org.id}/profile`, f);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['invoices'] });
      onClose();
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  return (
    <Modal open onClose={onClose} title={`${org.name} · billing`} size="lg"
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" form="fm-billing" disabled={busy || !f}>{busy && <Spinner />} Save</button></>}>
      {!f ? <Loading /> : (
        <form id="fm-billing" className="form-grid" onSubmit={save}>
          <Field label="Billing cycle"><select className="input" value={f.billing_cycle} onChange={set('billing_cycle')}>
            <option value="per_submission">Per submission</option><option value="monthly">Monthly</option></select></Field>
          <Field label="Name on invoices"><input className="input" value={f.legal_name} placeholder={org.name} onChange={set('legal_name')} /></Field>
          <div className="span-2"><Field label="Billing address"><input className="input" value={f.address} onChange={set('address')} /></Field></div>
          <Field label="Country" required><input className="input" required value={f.country} onChange={set('country')} /></Field>
          <Field label="State"><input className="input" value={f.state} onChange={set('state')} /></Field>
          <Field label="State code"><input className="input" maxLength={5} value={f.state_code} onChange={set('state_code')} /></Field>
          <Field label="GSTIN"><input className="input" maxLength={20} value={f.gstin} onChange={set('gstin')} /></Field>
          <Field label="Billing email"><input className="input" type="email" value={f.billing_email} onChange={set('billing_email')} /></Field>
          <Field label="Invoice reminders"><select className="input" value={f.reminder_mode} onChange={set('reminder_mode')}>
            <option value="default">Platform default</option><option value="off">Off</option><option value="custom">Custom</option></select></Field>
          {f.reminder_mode === 'custom' && <>
            <Field label="First reminder after (days)" required><input className="input" type="number" min={1} max={90} required value={f.reminder_after_days ?? ''} onChange={set('reminder_after_days')} /></Field>
            <Field label="Then every (days)" required><input className="input" type="number" min={1} max={90} required value={f.reminder_repeat_days ?? ''} onChange={set('reminder_repeat_days')} /></Field>
            <Field label="At most (reminders)" required><input className="input" type="number" min={0} max={20} required value={f.reminder_max ?? ''} onChange={set('reminder_max')} /></Field>
          </>}
          {f.financial_managers && <div className="span-2 small muted">Financial Manager{f.financial_managers.people.length === 1 ? '' : 's'}: {f.financial_managers.people.map((p) => p.name).join(', ')}
            {f.financial_managers.uses_default && ' (default)'}</div>}
        </form>
      )}
    </Modal>
  );
}
