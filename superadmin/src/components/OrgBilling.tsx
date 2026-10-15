/** A university / organisation's billing profile (tax place, GSTIN, billing cycle) on its Overview tab. */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, errorMessage } from '@/lib/api';
import { Badge, Field, Loading, Panel, Spinner, useToast } from '@/components/ui';

interface Profile {
  legal_name: string; address: string; state: string; state_code: string; country: string; gstin: string;
  billing_email: string; billing_cycle: 'per_submission' | 'monthly'; billing_cycle_label: string; missing: string[];
  financial_managers?: { uses_default: boolean; people: { id: number; name: string; email: string }[] };
  reminder_mode: 'default' | 'off' | 'custom'; reminder_after_days: number | null; reminder_repeat_days: number | null; reminder_max: number | null;
}

export function OrgBilling({ orgId, orgName }: { orgId: number; orgName: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const key = ['admin', 'billing', 'profile', orgId];
  const q = useQuery({ queryKey: key, queryFn: async () => (await api.get<Profile>(`/api/superadmin/billing/organisations/${orgId}/profile`)).data });
  const [form, setForm] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);
  if (q.isLoading) return <Panel title="Billing"><Loading /></Panel>;
  if (!q.data) return null;
  const f = form ?? q.data;
  const set = (k: keyof Profile) => (e: { target: { value: string } }) => setForm({ ...f, [k]: e.target.value } as Profile);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.put(`/api/superadmin/billing/organisations/${orgId}/profile`, f);
      toast.success(data.message);
      qc.setQueryData(key, data);
      setForm(null);
      void qc.invalidateQueries({ queryKey: ['admin', 'invoices'] });
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  const generate = async () => {
    try {
      const { data } = await api.post(`/api/billing/organisations/${orgId}/generate`, {});
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'invoices'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };

  return (
    <Panel title={`${orgName} billing`}
      actions={<div className="row-tight">
        {q.data.missing.length > 0 ? <Badge tone="danger">Incomplete</Badge> : <Badge tone="ok">{q.data.billing_cycle_label}</Badge>}
        <Link className="btn btn-ghost btn-sm" to={`/invoices/?organisation=${orgId}`}>Invoices</Link>
        {q.data.billing_cycle === 'monthly' && !q.data.missing.length && (
          <button className="btn btn-secondary btn-sm" onClick={generate}>Generate this month's invoice</button>)}
      </div>}>
      {q.data.missing.length > 0 && (
        <p className="small" style={{ marginTop: 0, color: 'var(--danger)' }}>
          Add the {q.data.missing.join(' and ')}: invoices are not generated until then (GST depends on it).</p>
      )}
      {q.data.financial_managers && (
        <p className="small" style={{ marginTop: 0 }}>
          <strong>Financial Manager{q.data.financial_managers.people.length === 1 ? '' : 's'}:</strong>{' '}
          {q.data.financial_managers.people.map((p) => p.name).join(', ') || '—'}
          <span className="muted"> · {q.data.financial_managers.uses_default ? 'default (assign one in the PoCs tab → Turacoz team)' : 'assigned to this workspace'}</span>
        </p>
      )}
      <form className="form-grid" onSubmit={save}>
        <Field label="Billing cycle" help="Per submission: an invoice for every request. Monthly: one invoice a month.">
          <select className="input" value={f.billing_cycle} onChange={set('billing_cycle')}>
            <option value="per_submission">Per submission</option><option value="monthly">Monthly</option>
          </select>
        </Field>
        <Field label="Name on invoices"><input className="input" value={f.legal_name} placeholder={orgName} onChange={set('legal_name')} /></Field>
        <div className="span-2"><Field label="Billing address"><input className="input" value={f.address} onChange={set('address')} /></Field></div>
        <Field label="Country" required><input className="input" required value={f.country} onChange={set('country')} /></Field>
        <Field label="State" help="Same state as Turacoz → CGST + SGST; other state → IGST."><input className="input" value={f.state} onChange={set('state')} /></Field>
        <Field label="State code"><input className="input" maxLength={5} value={f.state_code} onChange={set('state_code')} /></Field>
        <Field label="GSTIN"><input className="input" maxLength={20} value={f.gstin} onChange={set('gstin')} /></Field>
        <div className="span-2"><Field label="Billing email" help="Receives invoices too, besides the administrators.">
          <input className="input" type="email" value={f.billing_email} onChange={set('billing_email')} /></Field></div>
        <Field label="Invoice reminders" help={f.reminder_mode === 'default' ? 'As set in Billing Settings.' : f.reminder_mode === 'off' ? 'No reminders for this workspace.' : 'This workspace has its own schedule.'}>
          <select className="input" value={f.reminder_mode} onChange={set('reminder_mode')}>
            <option value="default">Platform default</option><option value="off">Off</option><option value="custom">Custom</option>
          </select>
        </Field>
        {f.reminder_mode === 'custom' ? (
          <div className="rm-days">
            <Field label="First after (days)" required><input className="input" type="number" min={1} max={90} required value={f.reminder_after_days ?? ''} onChange={set('reminder_after_days')} /></Field>
            <Field label="Then every (days)" required><input className="input" type="number" min={1} max={90} required value={f.reminder_repeat_days ?? ''} onChange={set('reminder_repeat_days')} /></Field>
            <Field label="At most" required><input className="input" type="number" min={0} max={20} required value={f.reminder_max ?? ''} onChange={set('reminder_max')} /></Field>
          </div>
        ) : <div />}
        <div className="span-2"><button className="btn btn-primary" disabled={busy}>{busy && <Spinner />} Save billing profile</button></div>
      </form>
    </Panel>
  );
}
