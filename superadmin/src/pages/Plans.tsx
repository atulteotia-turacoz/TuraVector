/**
 * Plans & Pricing — a plan is a set of tools at a price for a period, offered to individuals,
 * universities / organisations or both. Users pick plans at sign-up and on their Plans page;
 * existing subscribers keep what they bought when a plan changes.
 */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Star, Trash2 } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Badge, ErrorNotice, Field, Loading, Modal, PageHeader, Spinner, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';
import { money } from './RateCards';

export interface PlanRow {
  id: number; name: string; description: string; price: number; currency: string; billing_period: string;
  billing_period_label: string; trial_days: number; audience: string; audience_label: string; is_featured: boolean;
  is_active: boolean; sort_order: number; tax_percent: number; sac_code: string; tools: { key: string; name: string; is_active: boolean }[]; subscribers: number;
}
type Opt = { value: string; label: string };
interface Listing { plans: PlanRow[]; tools: { key: string; name: string; is_active: boolean; is_free: boolean }[]; periods: Opt[]; audiences: Opt[] }

const KEY = ['admin', 'subscriptions', 'plans'];
const blank = { name: '', description: '', price: '', billing_period: 'monthly', trial_days: '0', audience: 'all',
  tool_keys: [] as string[], is_featured: false, is_active: true, sort_order: 0, tax_percent: '18', sac_code: '' };

export default function Plans() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: async () => (await api.get<Listing>('/api/superadmin/subscriptions/plans')).data });
  const [editing, setEditing] = useState<PlanRow | 'new' | null>(null);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { plans, tools, periods, audiences } = q.data;

  const open = (p: PlanRow | 'new') => {
    setEditing(p);
    setForm(p === 'new' ? blank : { name: p.name, description: p.description, price: String(p.price), billing_period: p.billing_period,
      trial_days: String(p.trial_days), audience: p.audience, tool_keys: p.tools.map((t) => t.key), is_featured: p.is_featured,
      is_active: p.is_active, sort_order: p.sort_order, tax_percent: String(p.tax_percent), sac_code: p.sac_code });
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.tool_keys.length) { toast.error('Choose at least one tool for the plan.'); return; }
    setBusy(true);
    try {
      const body = { ...form, price: form.price || 0, trial_days: Number(form.trial_days) || 0, tax_percent: form.tax_percent || 0 };
      const { data } = editing === 'new'
        ? await api.post('/api/superadmin/subscriptions/plans', body)
        : await api.put(`/api/superadmin/subscriptions/plans/${(editing as PlanRow).id}`, body);
      toast.success(data.message);
      setEditing(null);
      void qc.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  const remove = async (p: PlanRow) => {
    if (!(await confirm({ title: 'Delete plan', danger: true, confirmLabel: 'Delete', message: `Delete the plan "${p.name}"?` }))) return;
    try {
      const { data } = await api.delete(`/api/superadmin/subscriptions/plans/${p.id}`);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const toggleTool = (key: string) => setForm((f) => ({
    ...f, tool_keys: f.tool_keys.includes(key) ? f.tool_keys.filter((k) => k !== key) : [...f.tool_keys, key] }));

  return (
    <>
      <Crumbs items={[{ label: 'Plans & Pricing' }]} />
      <PageHeader title="Plans & pricing"
        subtitle={<>Bundle <Link className="act" to="/tools/">tools</Link> into plans and set their price. Users choose a plan at sign-up and on their Plans page; to charge per tool, make a plan with one tool.</>}
        actions={<button className="btn btn-primary" onClick={() => open('new')}><Plus size={15} /> Add plan</button>} />

      <section className="panel">
        {plans.length === 0 ? (
          <div className="panel-body"><p className="muted" style={{ margin: 0 }}>No plans yet. Add a plan to start selling tools — users then see it at sign-up and on their home page.</p></div>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>Plan</th><th>Tools</th><th className="num">Price</th><th>For</th><th className="num">Subscribers</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {plans.map((p) => (
                  <tr key={p.id}>
                    <td><strong className="row-tight">{p.name}{p.is_featured && <Star size={13} style={{ color: 'var(--accent)' }} />}</strong>
                      {p.description && <span className="tiny faint" style={{ display: 'block' }}>{p.description}</span>}</td>
                    <td className="small">{p.tools.map((t) => t.name).join(', ')}</td>
                    <td className="num">{p.price > 0 ? money(p.price, p.currency) : 'Free'}
                      <span className="tiny faint" style={{ display: 'block' }}>{p.price > 0 && p.tax_percent > 0 ? `+ ${p.tax_percent}% GST · ` : ''}{p.billing_period_label}{p.trial_days > 0 ? ` · ${p.trial_days}-day trial` : ''}</span></td>
                    <td className="small">{p.audience_label}</td>
                    <td className="num">{p.subscribers || <span className="faint">—</span>}</td>
                    <td>{p.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Inactive</Badge>}</td>
                    <td><div className="row-tight nowrap">
                      <button className="btn btn-ghost btn-icon" title="Edit" onClick={() => open(p)}><Pencil size={14} /></button>
                      <button className="btn btn-ghost btn-icon" title="Delete" onClick={() => remove(p)}><Trash2 size={14} /></button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === 'new' ? 'Add plan' : 'Edit plan'}
        footer={<>
          <button className="btn btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
          <button className="btn btn-primary" form="plan-form" disabled={busy}>{busy && <Spinner />} Save</button>
        </>}>
        <form id="plan-form" className="form-grid" onSubmit={save}>
          <div className="span-2"><Field label="Plan name" required><input className="input" required value={form.name} onChange={set('name')} placeholder="e.g. Researcher Pro" /></Field></div>
          <div className="span-2"><Field label="Description"><input className="input" maxLength={500} value={form.description} onChange={set('description')} /></Field></div>
          <div className="span-2">
            <Field label="Tools in this plan" required>
              <div className="stack" style={{ gap: 6 }}>
                {tools.map((t) => (
                  <label key={t.key} className="check">
                    <input type="checkbox" checked={form.tool_keys.includes(t.key)} onChange={() => toggleTool(t.key)} />
                    <span>{t.name}{!t.is_active && <span className="faint"> (off)</span>}{t.is_free && <span className="faint"> (free for all)</span>}</span>
                  </label>
                ))}
              </div>
            </Field>
          </div>
          <Field label="Price (INR)" required help="0 = free plan">
            <input className="input" type="number" min="0" step="0.01" required value={form.price} onChange={set('price')} />
          </Field>
          <Field label="GST (%)" help="Added on top of the price at checkout. 0 = no GST.">
            <input className="input" type="number" min="0" max="100" step="0.01" value={form.tax_percent} onChange={set('tax_percent')} />
          </Field>
          <Field label="SAC code" help="Printed on the tax invoice.">
            <input className="input" maxLength={20} value={form.sac_code} onChange={set('sac_code')} placeholder="e.g. 998431" />
          </Field>
          <Field label="Billing period" required>
            <select className="input" value={form.billing_period} onChange={set('billing_period')}>
              {periods.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </Field>
          <Field label="Free trial (days)" help="0 = no trial. Each workspace gets the trial once.">
            <input className="input" type="number" min="0" max="365" value={form.trial_days} onChange={set('trial_days')} />
          </Field>
          <Field label="Offered to" required>
            <select className="input" value={form.audience} onChange={set('audience')}>
              {audiences.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </Field>
          <Field label="Order" help="Lower numbers come first."><input className="input" type="number" value={form.sort_order} onChange={(e) => setForm((f) => ({ ...f, sort_order: Number(e.target.value) || 0 }))} /></Field>
          <Field label="Highlight">
            <label className="check"><input type="checkbox" checked={form.is_featured} onChange={(e) => setForm((f) => ({ ...f, is_featured: e.target.checked }))} /><span>Mark as popular</span></label>
          </Field>
          <div className="span-2"><Field label="Status">
            <label className="check"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
              <span>Active — can be chosen by users. Existing subscribers keep their plan either way.</span></label>
          </Field></div>
        </form>
      </Modal>
    </>
  );
}
