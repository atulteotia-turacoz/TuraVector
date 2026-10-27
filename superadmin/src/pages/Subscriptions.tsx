/**
 * Subscriptions — every workspace's plans: who bought what, payments due, and what ended. A plan can be
 * given to a workspace directly (paid offline, complimentary) and a subscription cancelled or extended.
 */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Gift, Search } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Badge, ErrorNotice, Field, Loading, Modal, PageHeader, Pagination, SearchSelect, Spinner, Stat, Tabs, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';
import { money } from './RateCards';
import type { PlanRow } from './Plans';

export interface SubRow {
  id: number; plan_name: string; tools: { key: string; name: string }[]; price: number; currency: string;
  billing_period_label: string; status: string; state: 'pending' | 'active' | 'scheduled' | 'expired' | 'cancelled';
  is_trial: boolean; source: string; starts_at: string | null; ends_at: string | null; paid_at: string | null;
  payment_ref: string; notes: string; created_at: string | null;
  tax_amount: number; total: number; invoice_id: number | null; cancelled_at: string | null;
  organisation: { id: number; name: string; kind: string };
}
export interface Resp { items: SubRow[]; total: number; page: number; pages: number; stats: { active_workspaces: number; pending: number; revenue: number } }
type State = '' | 'active' | 'pending' | 'expired' | 'cancelled';

export const TONE: Record<SubRow['state'], 'ok' | 'warn' | 'accent' | undefined> = { active: 'ok', scheduled: 'accent', pending: 'warn', expired: undefined, cancelled: undefined };
export const LABEL: Record<SubRow['state'], string> = { active: 'Active', scheduled: 'Starts later', pending: 'Awaiting payment', expired: 'Expired', cancelled: 'Cancelled' };
const SOURCE: Record<string, string> = { signup: 'Sign-up', self: 'Bought', admin: 'Given by admin' };

export default function Subscriptions() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [state, setState] = useState<State>('');
  const [params] = useSearchParams();
  const [search, setSearch] = useState(params.get('q') ?? '');
  const [term, setTerm] = useState(params.get('q') ?? '');
  const [page, setPage] = useState(1);
  const [giving, setGiving] = useState(false);
  const [extending, setExtending] = useState<SubRow | null>(null);
  const q = useQuery({
    queryKey: ['admin', 'subscriptions', 'list', state, term, page],
    queryFn: async () => (await api.get<Resp>('/api/superadmin/subscriptions', { params: { state, search: term, page } })).data,
    placeholderData: (prev) => prev,
  });

  const act = async (s: SubRow, action: 'cancel' | 'activate') => {
    const text = action === 'cancel'
      ? `Cancel ${s.plan_name} for ${s.organisation.name}? Its tools stop working for that workspace straight away.`
      : `Mark ${s.plan_name} for ${s.organisation.name} as paid (offline) and activate it?`;
    if (!(await confirm({ title: action === 'cancel' ? 'Cancel subscription' : 'Activate subscription', danger: action === 'cancel',
      confirmLabel: action === 'cancel' ? 'Cancel subscription' : 'Activate', message: text }))) return;
    try {
      const { data } = await api.post(`/api/superadmin/subscriptions/${s.id}`, { action });
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;

  return (
    <>
      <Crumbs items={[{ label: 'Subscriptions' }]} />
      <PageHeader title="Subscriptions" subtitle={<>Plans bought or given to each workspace. Plans are set up under <Link className="act" to="/plans/">Plans &amp; Pricing</Link>.</>}
        actions={<button className="btn btn-primary" onClick={() => setGiving(true)}><Gift size={15} /> Give a plan</button>} />

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <Stat value={d.stats.active_workspaces} label="Workspaces with a plan" />
        <Stat value={d.stats.pending} label="Awaiting payment" />
        <Stat value={money(d.stats.revenue)} label="Paid online / offline" />
      </div>

      <div className="row wrap between" style={{ marginBottom: 12 }}>
        <Tabs<State> value={state} onChange={(v) => { setState(v); setPage(1); }} tabs={[
          { value: '', label: 'All' }, { value: 'active', label: 'Active' }, { value: 'pending', label: 'Awaiting payment' },
          { value: 'expired', label: 'Expired' }, { value: 'cancelled', label: 'Cancelled' },
        ]} />
        <form className="row-tight" onSubmit={(e) => { e.preventDefault(); setTerm(search); setPage(1); }}>
          <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Workspace, plan or payment ref" />
          <button className="btn btn-secondary"><Search size={14} /></button>
        </form>
      </div>

      <section className="panel">
        {d.items.length === 0 ? (
          <div className="panel-body"><p className="muted" style={{ margin: 0 }}>No subscriptions found.</p></div>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>Workspace</th><th>Plan</th><th className="num">Price</th><th>Period</th><th>Status</th><th>Payment</th><th>Actions</th></tr></thead>
              <tbody>
                {d.items.map((s) => (
                  <tr key={s.id}>
                    <td>{s.organisation.kind === 'individual'
                      ? <strong>{s.organisation.name}</strong>
                      : <Link className="act" to={`/organisations/${s.organisation.id}/`}><strong>{s.organisation.name}</strong></Link>}
                      <span className="tiny faint" style={{ display: 'block' }}>{s.organisation.kind}</span></td>
                    <td><strong>{s.plan_name}</strong><span className="tiny faint" style={{ display: 'block' }}>{s.tools.map((t) => t.name).join(', ')}</span></td>
                    <td className="num">{s.price > 0 ? money(s.total, s.currency) : 'Free'}
                      <span className="tiny faint" style={{ display: 'block' }}>{s.tax_amount > 0 ? `incl. ${money(s.tax_amount, s.currency)} GST · ` : ''}{s.billing_period_label}</span></td>
                    <td className="small nowrap">{s.starts_at ? formatDate(s.starts_at) : '—'} → {s.ends_at ? formatDate(s.ends_at) : s.status === 'active' ? 'no end' : '—'}</td>
                    <td><Badge tone={TONE[s.state]}>{s.is_trial && s.state === 'active' ? 'Free trial' : LABEL[s.state]}</Badge>
                      {s.cancelled_at && s.state === 'active' && <Badge tone="warn">Cancelled by workspace</Badge>}
                      <span className="tiny faint" style={{ display: 'block' }}>{SOURCE[s.source] ?? s.source}</span>
                      {s.notes.includes('refund') && <span className="tiny" style={{ display: 'block', color: 'var(--danger)' }}>{s.notes.slice(s.notes.indexOf('Cancelled before'))}</span>}</td>
                    <td className="small">{s.payment_ref || <span className="faint">—</span>}{s.paid_at && <span className="tiny faint" style={{ display: 'block' }}>{formatDate(s.paid_at)}</span>}
                      {s.invoice_id && <Link className="act tiny" style={{ display: 'block' }} to={`/invoices/${s.invoice_id}/`}>Invoice</Link>}</td>
                    <td><div className="row-tight nowrap">
                      {s.status === 'pending' && <button className="btn btn-secondary btn-sm" onClick={() => act(s, 'activate')}>Mark paid</button>}
                      {s.status === 'active' && <button className="btn btn-ghost btn-sm" onClick={() => setExtending(s)}>End date</button>}
                      {s.status !== 'cancelled' && <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }} onClick={() => act(s, 'cancel')}>Cancel</button>}
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <Pagination page={d.page} pages={d.pages} total={d.total} onChange={setPage} />

      {giving && <GivePlan onClose={() => setGiving(false)} />}
      {extending && <EndDate sub={extending} onClose={() => setExtending(null)} />}
    </>
  );
}

function GivePlan({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const plans = useQuery({ queryKey: ['admin', 'subscriptions', 'plans'], queryFn: async () => (await api.get<{ plans: PlanRow[] }>('/api/superadmin/subscriptions/plans')).data });
  const [orgs, setOrgs] = useState<{ value: number; label: string; hint?: string }[]>([]);
  const [orgId, setOrgId] = useState<number | null>(null);
  const [planId, setPlanId] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  const searchOrgs = async (term: string) => {
    const { data } = await api.get<{ items: { id: number; name: string; kind: string }[] }>('/api/superadmin/subscriptions/organisations', { params: { search: term } });
    setOrgs(data.items.map((o) => ({ value: o.id, label: o.name, hint: o.kind })));
  };

  useEffect(() => { void searchOrgs(''); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!orgId || !planId) { toast.error('Choose a workspace and a plan.'); return; }
    setBusy(true);
    try {
      const { data } = await api.post('/api/superadmin/subscriptions/assign', { organisation_id: orgId, plan_id: Number(planId), ends_at: endsAt || null, notes });
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
      onClose();
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };

  return (
    <Modal open onClose={onClose} title="Give a plan"
      footer={<>
        <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" form="give-plan" disabled={busy}>{busy && <Spinner />} Activate plan</button>
      </>}>
      <form id="give-plan" className="form-grid" onSubmit={submit}>
        <div className="span-2"><Field label="Workspace" required help="An individual's workspace or a university / organisation.">
          <SearchSelect options={orgs} value={orgId} onChange={(v) => setOrgId(v as number | null)} onSearch={searchOrgs} placeholder="Search workspaces…" />
        </Field></div>
        <div className="span-2"><Field label="Plan" required>
          <select className="input" value={planId} onChange={(e) => setPlanId(e.target.value)} required>
            <option value="">— Choose a plan —</option>
            {(plans.data?.plans ?? []).map((p) => <option key={p.id} value={p.id}>{p.name} · {p.price > 0 ? money(p.price) : 'Free'} · {p.billing_period_label}</option>)}
          </select>
        </Field></div>
        <Field label="Ends on" help="Empty = the plan's normal period."><input className="input" type="date" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} /></Field>
        <Field label="Note" help="e.g. paid by bank transfer, ref …"><input className="input" maxLength={300} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      </form>
    </Modal>
  );
}

function EndDate({ sub, onClose }: { sub: SubRow; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [endsAt, setEndsAt] = useState(sub.ends_at ? sub.ends_at.slice(0, 10) : '');
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post(`/api/superadmin/subscriptions/${sub.id}`, { action: 'set_end', ends_at: endsAt || null });
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
      onClose();
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  return (
    <Modal open onClose={onClose} title={`End date — ${sub.plan_name}`}
      footer={<>
        <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" form="sub-end" disabled={busy}>{busy && <Spinner />} Save</button>
      </>}>
      <form id="sub-end" onSubmit={submit}>
        <Field label="Ends on" help={`For ${sub.organisation.name}. Empty = no end date.`}>
          <input className="input" type="date" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
        </Field>
      </form>
    </Modal>
  );
}
