/**
 * Tools & Services — every tool a workspace can use. Built-in tools (TuraVector dashboards and the Tura
 * applications) can be renamed, made free or switched off; new applications are added with their link.
 * Tools are sold through Plans & Pricing; a free tool is available to everyone without a plan.
 */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Pencil, Plus, Trash2 } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Badge, ErrorNotice, Field, Loading, Modal, PageHeader, Spinner, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

export interface ToolRow {
  id: number; key: string; name: string; description: string; features: string[]; kind: 'dashboard' | 'app';
  icon: string; url: string; launch_url: string; default_url: string; is_builtin: boolean; is_free: boolean; is_active: boolean;
  sort_order: number; plan_count: number;
}
interface Listing { tools: ToolRow[]; icons: string[] }

const KEY = ['admin', 'subscriptions', 'tools'];
const blank = { name: '', key: '', description: '', features: '', url: '', icon: '', is_free: false, is_active: true, sort_order: 100 };

export default function Tools() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: async () => (await api.get<Listing>('/api/superadmin/subscriptions/tools')).data });
  const [editing, setEditing] = useState<ToolRow | 'new' | null>(null);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { tools, icons } = q.data;
  const current = editing !== null && editing !== 'new' ? editing : null;

  const open = (t: ToolRow | 'new') => {
    setEditing(t);
    setForm(t === 'new' ? blank : { name: t.name, key: t.key, description: t.description, features: t.features.join('\n'),
      url: t.url, icon: t.icon, is_free: t.is_free, is_active: t.is_active, sort_order: t.sort_order });
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { ...form, features: form.features.split('\n') };
      const { data } = editing === 'new'
        ? await api.post('/api/superadmin/subscriptions/tools', body)
        : await api.put(`/api/superadmin/subscriptions/tools/${(editing as ToolRow).id}`, body);
      toast.success(data.message);
      setEditing(null);
      void qc.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  const remove = async (t: ToolRow) => {
    if (!(await confirm({ title: 'Remove tool', danger: true, confirmLabel: 'Remove', message: `Remove "${t.name}"? Its card disappears for everyone.` }))) return;
    try {
      const { data } = await api.delete(`/api/superadmin/subscriptions/tools/${t.id}`);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const check = (k: 'is_free' | 'is_active') => (e: { target: { checked: boolean } }) => setForm((f) => ({ ...f, [k]: e.target.checked }));

  return (
    <>
      <Crumbs items={[{ label: 'Tools & Services' }]} />
      <PageHeader title="Tools & services"
        subtitle={<>Everything a workspace can use. Sell tools through <Link className="act" to="/plans/">Plans &amp; Pricing</Link>; a free tool is open to every user without a plan.</>}
        actions={<button className="btn btn-primary" onClick={() => open('new')}><Plus size={15} /> Add application</button>} />

      <section className="panel">
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr><th>Tool</th><th>Type</th><th>Link</th><th className="num">In plans</th><th>Access</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {tools.map((t) => (
                <tr key={t.id}>
                  <td><strong>{t.name}</strong> <span className="tiny faint">{t.key}</span>
                    {t.description && <span className="tiny faint" style={{ display: 'block' }}>{t.description}</span>}</td>
                  <td className="small">{t.kind === 'dashboard' ? 'TuraVector dashboard' : 'Application'}{t.is_builtin && <span className="tiny faint" style={{ display: 'block' }}>built in</span>}</td>
                  <td className="small">{t.launch_url
                    ? <a className="act row-tight" href={t.launch_url} target="_blank" rel="noreferrer">Open <ExternalLink size={12} /></a>
                    : <span className="faint">—</span>}</td>
                  <td className="num">{t.plan_count || <span className="faint">—</span>}</td>
                  <td>{t.is_free ? <Badge tone="accent">Free for all</Badge> : <span className="small muted">By plan</span>}</td>
                  <td>{t.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Off</Badge>}</td>
                  <td><div className="row-tight nowrap">
                    <button className="btn btn-ghost btn-icon" title="Edit" onClick={() => open(t)}><Pencil size={14} /></button>
                    {!t.is_builtin && (
                      <button className="btn btn-ghost btn-icon" title={t.plan_count ? 'In a plan — switch it off instead' : 'Remove'}
                        disabled={t.plan_count > 0} onClick={() => remove(t)}><Trash2 size={14} /></button>
                    )}
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <p className="small muted">A per-user setting under <Link className="act" to="/app-access/">Application Access</Link> always wins: "Hidden" removes a tool even when the user's plan includes it.</p>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === 'new' ? 'Add application' : `Edit ${(editing as ToolRow | null)?.name ?? ''}`}
        footer={<>
          <button className="btn btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
          <button className="btn btn-primary" form="tool-form" disabled={busy}>{busy && <Spinner />} Save</button>
        </>}>
        <form id="tool-form" className="form-grid" onSubmit={save}>
          <div className="span-2"><Field label="Name" required><input className="input" required value={form.name} onChange={set('name')} placeholder="e.g. Tura Statistics" /></Field></div>
          {editing === 'new' && (
            <div className="span-2"><Field label="Key" help="Optional. A short id; made from the name when empty. Can't be changed later.">
              <input className="input" value={form.key} onChange={set('key')} placeholder="e.g. tura_stats" /></Field></div>
          )}
          {current?.kind !== 'dashboard' && (current?.is_builtin ? (
            <div className="span-2"><Field label="Link" help={<>Where the card opens (in a new tab). Leave empty to use the server setting: {current.default_url || '—'}.
              When single sign-on is set up for this application on the server, the card opens its sign-on address instead.</>}>
              <input className="input" type="url" value={form.url} onChange={set('url')} placeholder={current.default_url || 'https://'} /></Field></div>
          ) : (
            <div className="span-2"><Field label="Link" required help="Where the card opens (in a new tab).">
              <input className="input" type="url" required value={form.url} onChange={set('url')} placeholder="https://" /></Field></div>
          ))}
          <div className="span-2"><Field label="Description"><input className="input" maxLength={500} value={form.description} onChange={set('description')} /></Field></div>
          <div className="span-2"><Field label="Features" help="One per line — shown as bullet points on the card.">
            <textarea className="input" rows={4} value={form.features} onChange={set('features')} /></Field></div>
          <Field label="Icon">
            <select className="input" value={form.icon} onChange={set('icon')}>
              <option value="">Default</option>
              {icons.map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
          </Field>
          <Field label="Order" help="Lower numbers come first."><input className="input" type="number" value={form.sort_order} onChange={(e) => setForm((f) => ({ ...f, sort_order: Number(e.target.value) || 0 }))} /></Field>
          <Field label="Access">
            <label className="check"><input type="checkbox" checked={form.is_free} onChange={check('is_free')} /><span>Free for every user (no plan needed)</span></label>
          </Field>
          <Field label="Status">
            <label className="check"><input type="checkbox" checked={form.is_active} onChange={check('is_active')} /><span>Active — shown to users</span></label>
          </Field>
        </form>
      </Modal>
    </>
  );
}
