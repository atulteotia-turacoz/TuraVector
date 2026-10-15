/** Billing settings: Turacoz's GST details on every invoice, the invoice number prefix, and who approves invoices. */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { UserPlus, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Field, Loading, PageHeader, Panel, Spinner, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

interface Settings {
  company_name: string; address: string; state: string; state_code: string; country: string; gstin: string; pan: string;
  email: string; phone: string; invoice_prefix: string; bank_details: string; terms: string; next_number: string;
  reminders_enabled: boolean; reminder_after_days: number; reminder_repeat_days: number; reminder_max: number;
  remind_turacoz: boolean; remind_client: boolean; remind_payment: boolean;
}
interface Approvers {
  approvers: { id: number; user_id: number; name: string; email: string; since: string | null }[];
  candidates: { user_id: number; name: string; email: string }[];
  assigned: { id: number; organisation_id: number; organisation: string; user_id: number; name: string; email: string }[];
}

export default function BillingSettings() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ['admin', 'billing', 'settings'], queryFn: async () => (await api.get<Settings>('/api/superadmin/billing/settings')).data });
  const a = useQuery({ queryKey: ['admin', 'billing', 'approvers'], queryFn: async () => (await api.get<Approvers>('/api/superadmin/billing/approvers')).data });
  const [form, setForm] = useState<Settings | null>(null);
  const [pick, setPick] = useState('');
  const [busy, setBusy] = useState(false);

  if (s.isLoading || a.isLoading) return <Loading />;
  if (s.error || !s.data) return <ErrorNotice error={s.error} />;
  const f = form ?? s.data;
  const set = (k: keyof Settings) => (e: { target: { value: string } }) => setForm({ ...f, [k]: e.target.value });
  const tick = (k: keyof Settings) => (e: { target: { checked: boolean } }) => setForm({ ...f, [k]: e.target.checked });
  const runNow = async () => {
    try { toast.success((await api.post('/api/superadmin/billing/reminders/run')).data.message); }
    catch (err) { toast.error(errorMessage(err)); }
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.put('/api/superadmin/billing/settings', f);
      toast.success(data.message);
      qc.setQueryData(['admin', 'billing', 'settings'], data);
      setForm(null);
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  const addApprover = async () => {
    if (!pick) return;
    try {
      const { data } = await api.post('/api/superadmin/billing/approvers', { user_id: Number(pick) });
      toast.success(data.message);
      setPick('');
      void qc.invalidateQueries({ queryKey: ['admin', 'billing', 'approvers'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const removeApprover = async (row: Approvers['approvers'][number]) => {
    if (!(await confirm({ title: 'Remove approver', danger: true, confirmLabel: 'Remove', message: `${row.name} will no longer approve invoices.` }))) return;
    try {
      const { data } = await api.delete(`/api/superadmin/billing/approvers/${row.id}`);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'billing', 'approvers'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };

  return (
    <>
      <Crumbs items={[{ label: 'Billing Settings' }]} />
      <PageHeader title="Billing settings"
        subtitle="Turacoz's details printed on every invoice. Your state decides the GST: the same state as the client → CGST + SGST, another state → IGST." />
      <div className="grid-2 bs-grid">
        <Panel title="Company details (seller)">
          <form id="billing-settings" className="form-grid" onSubmit={save}>
            <div className="span-2"><Field label="Company name" required><input className="input" required value={f.company_name} onChange={set('company_name')} /></Field></div>
            <div className="span-2"><Field label="Address"><textarea className="input" rows={2} value={f.address} onChange={set('address')} /></Field></div>
            <Field label="State" required><input className="input" required value={f.state} onChange={set('state')} /></Field>
            <Field label="State code" help="GST code, e.g. 07 for Delhi"><input className="input" maxLength={5} value={f.state_code} onChange={set('state_code')} /></Field>
            <Field label="Country"><input className="input" value={f.country} onChange={set('country')} /></Field>
            <Field label="GSTIN"><input className="input" maxLength={20} value={f.gstin} onChange={set('gstin')} /></Field>
            <Field label="PAN"><input className="input" maxLength={20} value={f.pan} onChange={set('pan')} /></Field>
            <Field label="Billing email"><input className="input" type="email" value={f.email} onChange={set('email')} /></Field>
            <Field label="Phone"><input className="input" value={f.phone} onChange={set('phone')} /></Field>
            <Field label="Invoice prefix" required help={`Next invoice: ${s.data.next_number}`}>
              <input className="input" required maxLength={6} value={f.invoice_prefix} onChange={set('invoice_prefix')} /></Field>
            <div className="span-2"><Field label="Bank details" help="Printed on the invoice for bank transfers.">
              <textarea className="input" rows={3} value={f.bank_details} onChange={set('bank_details')} /></Field></div>
            <div className="span-2"><Field label="Terms"><textarea className="input" rows={2} value={f.terms} onChange={set('terms')} /></Field></div>
            <div className="span-2"><button className="btn btn-primary" disabled={busy}>{busy && <Spinner />} Save settings</button></div>
          </form>
        </Panel>
        <div className="stack-lg">
        <Panel title="Reminders" actions={<button className="btn btn-ghost btn-sm" onClick={runNow}>Send due reminders now</button>}>
          <p className="small muted" style={{ marginTop: 0 }}>
            Platform default for every university and organisation. A workspace can switch reminders off or set its own days on its Overview page.
            Due reminders are checked every hour.</p>
          <div className="stack">
            <label className="check"><input type="checkbox" form="billing-settings" checked={f.reminders_enabled} onChange={tick('reminders_enabled')} />
              <span><strong>Send invoice reminders</strong></span></label>
            <fieldset className="stack" disabled={!f.reminders_enabled} style={{ border: 0, padding: 0, margin: 0, opacity: f.reminders_enabled ? 1 : 0.5 }}>
              <div className="rm-days">
                <Field label="First reminder after" help="days in a stage">
                  <input className="input" form="billing-settings" type="number" min={1} max={90} value={f.reminder_after_days} onChange={set('reminder_after_days')} /></Field>
                <Field label="Then every" help="days">
                  <input className="input" form="billing-settings" type="number" min={1} max={90} value={f.reminder_repeat_days} onChange={set('reminder_repeat_days')} /></Field>
                <Field label="At most" help="reminders per stage">
                  <input className="input" form="billing-settings" type="number" min={0} max={20} value={f.reminder_max} onChange={set('reminder_max')} /></Field>
              </div>
              <span className="small muted">Remind about invoices that are…</span>
              <label className="check"><input type="checkbox" form="billing-settings" checked={f.remind_turacoz} onChange={tick('remind_turacoz')} />
                <span>waiting for Turacoz approval <span className="faint">→ invoice approvers</span></span></label>
              <label className="check"><input type="checkbox" form="billing-settings" checked={f.remind_client} onChange={tick('remind_client')} />
                <span>waiting for the client's approval <span className="faint">→ university administrators</span></span></label>
              <label className="check"><input type="checkbox" form="billing-settings" checked={f.remind_payment} onChange={tick('remind_payment')} />
                <span>approved but unpaid <span className="faint">→ university administrators</span></span></label>
            </fieldset>
            <button className="btn btn-primary" form="billing-settings" disabled={busy} style={{ justifySelf: 'start' }}>{busy && <Spinner />} Save reminders</button>
          </div>
        </Panel>
        <Panel title="Default Financial Managers" flush>
          <div className="panel-body small muted" style={{ paddingBottom: 0 }}>
            They approve the invoices of every university and organisation that has no Financial Manager of its own.
            A university's own Financial Manager is assigned on its page (PoCs tab → Turacoz team → role Financial Manager).
            Financial Managers work in the TuraVector app (Finance Dashboard, Invoices); superadmins can always approve.
          </div>
          <div className="org-add">
            <select className="input grow" value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Turacoz team member">
              <option value="">Add a default Financial Manager…</option>
              {(a.data?.candidates ?? []).map((c) => <option key={c.user_id} value={c.user_id}>{c.name} · {c.email}</option>)}
            </select>
            <button className="btn btn-primary" disabled={!pick} onClick={addApprover}><UserPlus size={14} /> Add</button>
          </div>
          {(a.data?.approvers ?? []).length === 0
            ? <div className="panel-body muted small">No default Financial Manager yet — invoices of universities without their own go to the superadmins.</div>
            : (
              <table className="tbl">
                <thead><tr><th>Name</th><th>Since</th><th /></tr></thead>
                <tbody>
                  {a.data!.approvers.map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.name}</strong><span className="tiny faint" style={{ display: 'block' }}>{r.email}</span></td>
                      <td className="small nowrap">{r.since ? formatDate(r.since) : ''}</td>
                      <td><button className="btn btn-ghost btn-sm" onClick={() => removeApprover(r)}><X size={13} /> Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </Panel>
        <Panel title="Financial Managers by university" flush>
          {(a.data?.assigned ?? []).length === 0
            ? <div className="panel-body muted small">No university has its own Financial Manager; the defaults handle all of them.</div>
            : (
              <table className="tbl">
                <thead><tr><th>University / organisation</th><th>Financial Manager</th></tr></thead>
                <tbody>{a.data!.assigned.map((r) => (
                  <tr key={r.id}>
                    <td><Link className="act" to={`/organisations/${r.organisation_id}/?tab=pocs`}>{r.organisation}</Link></td>
                    <td><strong>{r.name}</strong><span className="tiny faint" style={{ display: 'block' }}>{r.email}</span></td>
                  </tr>))}</tbody>
              </table>
            )}
        </Panel>
        </div>
      </div>
    </>
  );
}
