/** Plans & billing for the signed-in user's workspace: current plans, payments due, and plans to buy.
 * Individuals manage their own workspace; a university / organisation's plans are managed by its admin. */
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, CreditCard, RefreshCw, RotateCcw, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Loading, Spinner, useConfirm, useToast } from '@/components/ui';
import { NotificationBell, UserMenu } from '@/layouts/AppShell';
import { ThemePicker } from '@/components/ThemePicker';
import { BareFrame } from '@/features/auth/components';
import { payWithRazorpay } from '@/features/billing/razorpay';
import { PlanCard, STATE_LABEL, ToolIcon, dueLabel, money, type Plan, type Subscription, type Tool } from './shared';
import BillingSection, { BILLING_KEY } from './BillingSection';

interface Overview {
  workspace: { name: string; kind: string } | null;
  can_manage: boolean;
  payment_available: boolean;
  tools: (Tool & { has_access: boolean })[];
  plans: Plan[];
  subscriptions: Subscription[];
  trial_available: boolean;
  billing_missing: string[];
}

const KEY = ['subscriptions', 'overview'];

export default function PlansPage() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState<string | null>(null);
  const [toolFilter, setToolFilter] = useState<string | null>(params.get('tool'));
  const autoPaid = useRef(false);
  const q = useQuery({ queryKey: KEY, queryFn: async () => (await api.get<Overview>('/api/subscriptions')).data });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: KEY });
    void qc.invalidateQueries({ queryKey: BILLING_KEY });
    void qc.invalidateQueries({ queryKey: ['auth', 'dashboard-selection'] });
  };

  const pay = async (sub: { id: number }) => {
    setBusy(`pay-${sub.id}`);
    try {
      const { data: order } = await api.post(`/api/subscriptions/${sub.id}/pay`);
      const result = await payWithRazorpay(order);
      if (result) {
        const { data } = await api.post(`/api/subscriptions/${sub.id}/pay/verify`, result);
        toast.success(data.message);
      }
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(null);
    refresh();
  };

  // ?pay=<id> (after sign-up with a paid plan) opens the payment window once
  useEffect(() => {
    const id = Number(params.get('pay'));
    if (!id || autoPaid.current || !q.data) return;
    autoPaid.current = true;
    setParams((p) => { p.delete('pay'); return p; }, { replace: true });
    const sub = q.data.subscriptions.find((s) => s.id === id && s.status === 'pending');
    // GST depends on the billing details: ask for them first (the notice above the payment says so)
    if (sub && q.data.billing_missing.length) document.getElementById('billing-details')?.scrollIntoView({ behavior: 'smooth' });
    else if (sub && q.data.payment_available) void pay(sub);
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const subscribe = async (plan: Plan) => {
    setBusy(`plan-${plan.id}`);
    try {
      const { data } = await api.post('/api/subscriptions/subscribe', { plan_id: plan.id });
      setBusy(null);
      if (data.payment_required) {
        refresh();
        await pay(data.subscription);
        return;
      }
      toast.success(data.message);
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(null);
    refresh();
  };

  const renew = async (sub: Subscription) => {
    setBusy(`renew-${sub.id}`);
    try {
      const { data } = await api.post(`/api/subscriptions/${sub.id}/renew`);
      setBusy(null);
      if (data.payment_required) { refresh(); await pay(data.subscription); return; }
      toast.success(data.message);
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(null);
    refresh();
  };

  const cancel = async (sub: Subscription) => {
    const end = sub.ends_at ? formatDate(sub.ends_at) : '';
    const message = sub.status === 'pending'
      ? `Cancel ${sub.plan_name}? It hasn't been paid yet, so nothing is charged.`
      : sub.state === 'scheduled'
        ? `Cancel ${sub.plan_name}? It hasn't started yet, so Turacoz will refund the ${dueLabel(sub)} you paid.`
        : sub.ends_at
          ? `Cancel ${sub.plan_name}? You keep its tools until ${end}; after that it stops. Payments already made are not refunded.`
          : `Cancel ${sub.plan_name}? Its tools are removed right away.`;
    if (!(await confirm({ title: 'Cancel plan', danger: true, confirmLabel: 'Cancel plan', message }))) return;
    try {
      const { data } = await api.post(`/api/subscriptions/${sub.id}/cancel`);
      toast.success(data.message);
    } catch (err) { toast.error(errorMessage(err)); }
    refresh();
  };

  const resume = async (sub: Subscription) => {
    try {
      const { data } = await api.post(`/api/subscriptions/${sub.id}/resume`);
      toast.success(data.message);
    } catch (err) { toast.error(errorMessage(err)); }
    refresh();
  };

  const right = <><ThemePicker /><NotificationBell /><UserMenu profilePath="/profile/" /></>;

  if (q.isLoading) return <BareFrame right={right} theme={false}><Loading /></BareFrame>;
  if (q.isError || !q.data) return <BareFrame right={right} theme={false}><div className="pl-page"><ErrorNotice error={q.error} /></div></BareFrame>;
  const d = q.data;
  const pending = d.subscriptions.filter((s) => s.status === 'pending');
  const current = d.subscriptions.filter((s) => s.state === 'active' || s.state === 'scheduled');
  const past = d.subscriptions.filter((s) => s.state === 'expired' || s.state === 'cancelled');
  const plans = toolFilter ? d.plans.filter((p) => p.tools.some((t) => t.key === toolFilter)) : d.plans;
  const filterTool = d.tools.find((t) => t.key === toolFilter);
  const isOrg = d.workspace && d.workspace.kind !== 'individual';
  // one free trial per workspace: once it's used, plans are bought straight away
  const trialFor = (p: Plan) => (p.price > 0 && d.trial_available ? p.trial_days : 0);
  const listed = (s: Subscription) => d.plans.some((p) => p.id === s.plan_id);

  const subRow = (s: Subscription, actions?: React.ReactNode) => (
    <div className="pl-sub" key={s.id}>
      <div className="pl-sub-main">
        <div className="row-tight"><strong>{s.plan_name}</strong>
          <span className={`badge ${STATE_LABEL[s.state].tone ? `badge-${STATE_LABEL[s.state].tone}` : ''}`}>{s.is_trial && s.state === 'active' ? 'Free trial' : STATE_LABEL[s.state].label}</span>
          {s.cancelled_at && s.state === 'active' && <span className="badge badge-warn">Cancelled</span>}</div>
        <div className="pl-sub-tools">{s.tools.map((t) => t.name).join(' · ')}</div>
      </div>
      <div className="pl-sub-meta">
        {s.status === 'pending' ? dueLabel(s)
          : s.state === 'cancelled' ? 'Cancelled'
            : s.ends_at ? <>{s.state === 'scheduled' ? `Starts ${formatDate(s.starts_at)} · ` : ''}{s.state === 'expired' ? 'Ended' : s.cancelled_at ? 'Access until' : s.is_trial ? 'Trial ends' : 'Renews / ends'} {formatDate(s.ends_at)}</>
              : 'No end date'}
      </div>
      {actions && <div className="row-tight">{actions}</div>}
    </div>
  );

  return (
    <BareFrame right={right} theme={false}>
      <div className="pl-page">
        <Link to="/home" className="row-tight small muted"><ArrowLeft size={14} /> Back to dashboards</Link>
        <div className="pl-page-head" style={{ marginTop: 12 }}>
          <h1>Plans &amp; tools</h1>
          <p>{d.can_manage
            ? `Choose the tools ${isOrg ? `${d.workspace!.name} needs` : 'you need'}. Every plan unlocks its tools right after payment.`
            : 'Plans for your workspace are managed by your university or organisation administrator.'}</p>
        </div>

        {d.can_manage && !d.payment_available && d.plans.some((p) => p.price > 0) && (
          <div className="notice notice-warn">Online payment isn't set up yet. To buy a paid plan, please contact Turacoz.</div>
        )}

        {pending.length > 0 && d.can_manage && (
          <section className="pl-section">
            <h2>Awaiting payment</h2>
            {d.billing_missing.length > 0 && (
              <div className="notice notice-warn" style={{ marginBottom: 10 }}>
                Add your <a className="act" href="#billing-details">billing details</a> before paying — GST on the invoice depends on your state.
              </div>
            )}
            {pending.map((s) => subRow(s, <>
              <button className="btn btn-primary btn-sm" disabled={!!busy || !d.payment_available || d.billing_missing.length > 0} onClick={() => pay(s)}>
                {busy === `pay-${s.id}` ? <Spinner /> : <CreditCard size={14} />} Pay {money(s.total, s.currency)}</button>
              <button className="btn btn-ghost btn-sm" onClick={() => cancel(s)}><X size={14} /> Cancel</button>
            </>))}
          </section>
        )}

        <section className="pl-section">
          <h2>Your plans</h2>
          {current.length === 0
            ? <div className="pl-sub"><span className="muted small">No plan yet{d.tools.some((t) => t.is_free) ? ' — you have the free tools.' : '.'}</span></div>
            : current.map((s) => subRow(s, d.can_manage ? <>
              {s.plan_id && s.price > 0 && s.ends_at && !s.cancelled_at && s.state === 'active' && (
                <button className="btn btn-secondary btn-sm" disabled={!!busy || !d.payment_available} onClick={() => renew(s)}>
                  {busy === `renew-${s.id}` ? <Spinner /> : <RefreshCw size={14} />} {s.is_trial ? 'Buy now' : 'Renew'}</button>
              )}
              {s.cancelled_at && s.state === 'active' && (
                <button className="btn btn-secondary btn-sm" onClick={() => resume(s)}><RotateCcw size={14} /> Keep plan</button>
              )}
              {s.can_cancel && <button className="btn btn-ghost btn-sm" onClick={() => cancel(s)}><X size={14} /> Cancel</button>}
            </> : undefined))}
        </section>

        <section className="pl-section">
          <h2>Your tools</h2>
          <div className="pl-filter">
            {d.tools.filter((t) => t.has_access || d.plans.some((p) => p.tools.some((pt) => pt.key === t.key))).map((t) => (
              <span key={t.key} className={`pl-chip ${t.has_access ? 'is-on' : ''}`} title={t.description}>
                <ToolIcon icon={t.icon} size={14} /> {t.name}{!t.has_access && <span className="faint">· locked</span>}
              </span>
            ))}
          </div>
        </section>

        {d.plans.length > 0 && (
          <section className="pl-section">
            <h2>{d.can_manage ? 'Available plans' : 'Plans'}</h2>
            <div className="pl-filter">
              <button type="button" className={`pl-chip ${!toolFilter ? 'is-on' : ''}`} onClick={() => setToolFilter(null)}>All plans</button>
              {d.tools.filter((t) => d.plans.some((p) => p.tools.some((pt) => pt.key === t.key))).map((t) => (
                <button type="button" key={t.key} className={`pl-chip ${toolFilter === t.key ? 'is-on' : ''}`}
                  onClick={() => setToolFilter(toolFilter === t.key ? null : t.key)}>
                  <ToolIcon icon={t.icon} size={14} /> {t.name}
                </button>
              ))}
            </div>
            {filterTool && <p className="small muted" style={{ marginTop: 0 }}>Plans that include {filterTool.name}.</p>}
            <div className="pl-grid">
              {plans.map((p) => (
                <PlanCard key={p.id} plan={{ ...p, trial_days: trialFor(p) }}
                  action={d.can_manage ? (
                    <button className={`btn ${p.is_featured ? 'btn-primary' : 'btn-secondary'}`} disabled={!!busy || (p.price > 0 && !trialFor(p) && !d.payment_available)}
                      onClick={() => subscribe(p)}>
                      {busy === `plan-${p.id}` && <Spinner />}
                      {p.price <= 0 ? 'Activate' : trialFor(p) ? `Start ${trialFor(p)}-day trial` : 'Buy plan'}
                    </button>
                  ) : undefined} />
              ))}
            </div>
          </section>
        )}

        {d.can_manage && d.workspace && <BillingSection workspaceName={d.workspace.name} />}

        {past.length > 0 && (
          <section className="pl-section">
            <h2>History</h2>
            {past.map((s) => subRow(s, d.can_manage && s.state === 'expired' && s.price > 0 && listed(s) ? (
              <button className="btn btn-secondary btn-sm" disabled={!!busy || !d.payment_available} onClick={() => renew(s)}>
                {busy === `renew-${s.id}` ? <Spinner /> : <RefreshCw size={14} />} Buy again</button>
            ) : undefined))}
          </section>
        )}
      </div>
    </BareFrame>
  );
}
