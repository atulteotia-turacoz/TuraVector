/**
 * Standard rate card — every billable service with its standard rate. A university / organisation's
 * own rate card (Organisations → Overview) is built from these services, at its own rates.
 */
import { useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Badge, ErrorNotice, Field, Loading, Modal, PageHeader, Spinner, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

export interface RateServiceRow {
  id: number; name: string; description: string; unit: string; unit_label: string; standard_rate: number;
  tax_percent: number; currency: string; is_active: boolean; sort_order: number; used_by: number;
  sac_code: string; tax_overseas: boolean;
}
interface Listing { services: RateServiceRow[]; units: { value: string; label: string }[] }

export function money(v: number, currency = 'INR') {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency, minimumFractionDigits: 2 }).format(v);
}

const KEY = ['admin', 'rates', 'services'];
const blank = { name: '', description: '', unit: '', standard_rate: '', tax_percent: '18', sac_code: '', tax_overseas: false, is_active: true, sort_order: 0 };

export default function RateCards() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: async () => (await api.get<Listing>('/api/superadmin/rates/services')).data });
  const [editing, setEditing] = useState<RateServiceRow | 'new' | null>(null);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { services, units } = q.data;

  const open = (s: RateServiceRow | 'new') => {
    setEditing(s);
    setForm(s === 'new' ? blank : { name: s.name, description: s.description, unit: s.unit, standard_rate: String(s.standard_rate),
      tax_percent: String(s.tax_percent), sac_code: s.sac_code, tax_overseas: s.tax_overseas, is_active: s.is_active, sort_order: s.sort_order });
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { ...form, standard_rate: form.standard_rate || 0, tax_percent: form.tax_percent || 0 };
      const { data } = editing === 'new'
        ? await api.post('/api/superadmin/rates/services', body)
        : await api.put(`/api/superadmin/rates/services/${(editing as RateServiceRow).id}`, body);
      toast.success(data.message);
      setEditing(null);
      void qc.invalidateQueries({ queryKey: ['admin', 'rates'] });
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  const remove = async (s: RateServiceRow) => {
    if (!(await confirm({ title: 'Remove service', danger: true, confirmLabel: 'Remove',
      message: `Remove "${s.name}" from the standard rate card?` }))) return;
    try {
      const { data } = await api.delete(`/api/superadmin/rates/services/${s.id}`);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'rates'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <>
      <Crumbs items={[{ label: 'Rate Cards' }]} />
      <PageHeader title="Standard rate card"
        subtitle="Every service Turacoz offers, at its standard rate. A university's own rate card is built from these services — add a new service here first."
        actions={<button className="btn btn-primary" onClick={() => open('new')}><Plus size={15} /> Add service</button>} />

      <section className="panel">
        {services.length === 0 ? (
          <div className="panel-body">
            <p className="muted" style={{ margin: 0 }}>No services yet. Add the services you offer and their standard rates.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>Service</th><th>Unit</th><th className="num">Standard rate</th><th className="num">Tax</th>
                <th className="num">On rate cards</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {services.map((s) => (
                  <tr key={s.id}>
                    <td><strong>{s.name}</strong>{s.description && <span className="tiny faint" style={{ display: 'block' }}>{s.description}</span>}</td>
                    <td className="small">{s.unit_label || <span className="faint">—</span>}</td>
                    <td className="num">{money(s.standard_rate, s.currency)}</td>
                    <td className="num">{s.tax_percent}%{s.tax_overseas && <span className="tiny faint" style={{ display: 'block' }}>also abroad</span>}</td>
                    <td className="num">{s.used_by ? `${s.used_by} workspace${s.used_by === 1 ? '' : 's'}` : <span className="faint">—</span>}</td>
                    <td>{s.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Inactive</Badge>}</td>
                    <td><div className="row-tight nowrap">
                      <button className="btn btn-ghost btn-icon" title="Edit" onClick={() => open(s)}><Pencil size={14} /></button>
                      <button className="btn btn-ghost btn-icon" title={s.used_by ? 'On a rate card — mark it inactive instead' : 'Remove'}
                        disabled={s.used_by > 0} onClick={() => remove(s)}><Trash2 size={14} /></button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === 'new' ? 'Add service' : 'Edit service'}
        footer={<>
          <button className="btn btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
          <button className="btn btn-primary" form="rate-service" disabled={busy}>{busy && <Spinner />} Save</button>
        </>}>
        <form id="rate-service" className="form-grid" onSubmit={save}>
          <div className="span-2"><Field label="Service name" required><input className="input" required value={form.name} onChange={set('name')} placeholder="e.g. Manuscript review" /></Field></div>
          <div className="span-2"><Field label="Description"><input className="input" value={form.description} onChange={set('description')} /></Field></div>
          <Field label="Unit" help="Optional — how the rate is charged.">
            <select className="input" value={form.unit} onChange={set('unit')}>
              <option value="">— No unit —</option>
              {units.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
            </select>
          </Field>
          <Field label="Standard rate (INR)" required>
            <input className="input" type="number" min="0" step="0.01" required value={form.standard_rate} onChange={set('standard_rate')} />
          </Field>
          <Field label="Tax %" help="e.g. 18 for GST 18%">
            <input className="input" type="number" min="0" max="100" step="0.01" value={form.tax_percent} onChange={set('tax_percent')} />
          </Field>
          <Field label="SAC code" help="GST service code printed on invoices, e.g. 998311">
            <input className="input" maxLength={20} value={form.sac_code} onChange={set('sac_code')} />
          </Field>
          <Field label="Overseas clients">
            <label className="check"><input type="checkbox" checked={form.tax_overseas} onChange={(e) => setForm((f) => ({ ...f, tax_overseas: e.target.checked }))} />
              <span>Charge tax to clients outside India</span></label>
          </Field>
          <Field label="Status">
            <label className="check"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
              <span>Active — can be added to rate cards</span></label>
          </Field>
        </form>
      </Modal>
    </>
  );
}
