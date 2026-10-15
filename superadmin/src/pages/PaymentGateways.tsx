/**
 * Payment Gateways — keys and status of Stripe, Razorpay and CCAvenue. One gateway is active: every
 * payment goes through it. Secret keys are stored encrypted and never shown again after saving.
 */
import { useEffect, useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, CircleAlert, ExternalLink, PlugZap, Power, Star } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { Badge, ErrorNotice, Field, Loading, PageHeader, Spinner, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

interface GatewayField { key: string; label: string; secret: boolean; required: boolean; help: string; value: string; is_set: boolean; preview: string }
interface Gateway {
  code: string; name: string; description: string; docs_url: string; is_enabled: boolean; is_active: boolean;
  mode: 'test' | 'live'; currency: string; fields: GatewayField[]; missing: string[]; secrets_unreadable: boolean;
  last_tested_at: string | null; last_test_ok: boolean | null; last_test_message: string;
}
interface Listing {
  gateways: Gateway[]; modes: string[]; currencies: string[];
  checkout: { gateway: string | null; name?: string; mode?: string; not_configured?: string };
}

const KEY = ['admin', 'payment-gateways'];

export default function PaymentGateways() {
  const q = useQuery({ queryKey: KEY, queryFn: async () => (await api.get<Listing>('/api/superadmin/payment-gateways')).data });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;
  const active = d.gateways.find((g) => g.is_active);

  return (
    <>
      <Crumbs items={[{ label: 'Payment Gateways' }]} />
      <PageHeader title="Payment Gateways"
        subtitle="Keys for each payment provider. Exactly one gateway is active: every payment on TuraVector goes through it." />
      <div className={`notice ${d.checkout.gateway ? 'notice-ok' : 'notice-warn'} pg-status`}>
        {d.checkout.gateway
          ? <><CheckCircle2 size={16} /> Checkout uses <strong>{d.checkout.name}</strong> in <strong>{d.checkout.mode}</strong> mode.</>
          : active
            ? <><CircleAlert size={16} /> <strong>{active.name}</strong> is the active gateway, but its keys are not complete yet ({active.missing.join(', ')}). Payments are off until they are added.</>
            : <><CircleAlert size={16} /> No active gateway — payments are off.</>}
      </div>
      <div className="pg-list">
        {d.gateways.map((g) => <GatewayCard key={g.code} g={g} modes={d.modes} currencies={d.currencies} />)}
      </div>
    </>
  );
}

function GatewayCard({ g, modes, currencies }: { g: Gateway; modes: string[]; currencies: string[] }) {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [mode, setMode] = useState(g.mode);
  const [currency, setCurrency] = useState(g.currency);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { setMode(g.mode); setCurrency(g.currency); setValues({}); }, [g]);

  const run = async (what: string, call: () => Promise<{ data: any }>, quiet = false) => {
    setBusy(what);
    try {
      const { data } = await call();
      if (!quiet) toast.success(data.message);
      qc.setQueryData(KEY, data);
      return data;
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(null); }
  };
  const save = (e: FormEvent) => {
    e.preventDefault();
    const fields: Record<string, string> = {};
    g.fields.forEach((f) => { if (f.key in values) fields[f.key] = values[f.key]; });
    void run('save', () => api.post(`/api/superadmin/payment-gateways/${g.code}`, { mode, currency, fields }));
  };
  const test = async () => {
    const data = await run('test', () => api.post(`/api/superadmin/payment-gateways/${g.code}/test`), true);
    if (data) (data.ok ? toast.success : toast.error)(data.message);
  };
  const activate = async () => {
    if (!(await confirm({ title: `Use ${g.name} for payments`, confirmLabel: `Make ${g.name} active`,
      message: `All new payments will go through ${g.name}. The current active gateway stays configured but is no longer used.` }))) return;
    void run('activate', () => api.post(`/api/superadmin/payment-gateways/${g.code}/activate`));
  };
  const toggle = () => run('enable', () => api.post(`/api/superadmin/payment-gateways/${g.code}/enabled`, { enabled: !g.is_enabled }));
  const dirty = mode !== g.mode || currency !== g.currency || Object.values(values).some((v) => v !== undefined);

  return (
    <section className={`panel pg-card ${g.is_active ? 'is-active' : ''}`}>
      <div className="panel-head pg-head">
        <div>
          <h2 className="row-tight">{g.name}
            {g.is_active ? <Badge tone="accent">Active</Badge> : g.is_enabled ? <Badge tone="ok">Enabled</Badge> : <Badge>Disabled</Badge>}
            <Badge tone={g.mode === 'live' ? 'danger' : undefined}>{g.mode === 'live' ? 'Live' : 'Test'} mode</Badge>
          </h2>
          <p className="small muted">{g.description}</p>
        </div>
        <div className="row-tight wrap">
          {!g.is_active && <button className="btn btn-primary btn-sm" disabled={!!busy} onClick={activate}><Star size={13} /> Make active</button>}
          {!g.is_active && (
            <button className="btn btn-secondary btn-sm" disabled={!!busy} onClick={toggle}>
              <Power size={13} /> {g.is_enabled ? 'Disable' : 'Enable'}</button>
          )}
          <a className="btn btn-ghost btn-sm" href={g.docs_url} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Get keys</a>
        </div>
      </div>
      <form className="panel-body" onSubmit={save}>
        {g.secrets_unreadable && (
          <div className="notice notice-warn" style={{ marginBottom: 12 }}>
            The saved secret keys can no longer be read (the server's SECRET_KEY changed). Enter them again.
          </div>
        )}
        <div className="form-grid">
          <Field label="Mode" help="Use test keys while setting up; switch to live with live keys.">
            <select className="input" value={mode} onChange={(e) => setMode(e.target.value as Gateway['mode'])}>
              {modes.map((m) => <option key={m} value={m}>{m === 'live' ? 'Live' : 'Test'}</option>)}
            </select>
          </Field>
          <Field label="Currency">
            <select className="input" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {currencies.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          {g.fields.map((f) => (
            <Field key={f.key} label={f.label} required={f.required}
              help={f.secret && f.is_set ? `Saved (${f.preview}). Leave empty to keep it.` : f.help || undefined}>
              <input className="input mono" type={f.secret ? 'password' : 'text'} autoComplete="off"
                value={values[f.key] ?? (f.secret ? '' : f.value)}
                placeholder={f.secret && f.is_set ? '•••••••• (saved)' : ''}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} />
            </Field>
          ))}
        </div>
        <div className="pg-foot">
          <div className="small">
            {g.missing.length > 0
              ? <span className="pg-warn"><CircleAlert size={13} /> Missing: {g.missing.join(', ')}</span>
              : g.last_test_ok === null
                ? <span className="muted">Not tested since the keys were last saved.</span>
                : <span className={g.last_test_ok ? 'pg-ok' : 'pg-warn'}>
                    {g.last_test_ok ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />} {g.last_test_message}
                    {g.last_tested_at && <span className="faint"> · {formatDateTime(g.last_tested_at)}</span>}
                  </span>}
          </div>
          <div className="row-tight">
            <button type="button" className="btn btn-secondary btn-sm" disabled={!!busy || g.missing.length > 0 || dirty}
              title={dirty ? 'Save first' : undefined} onClick={test}>
              {busy === 'test' ? <Spinner /> : <PlugZap size={13} />} Test connection</button>
            <button className="btn btn-primary btn-sm" disabled={!!busy || !dirty}>{busy === 'save' && <Spinner />} Save</button>
          </div>
        </div>
      </form>
    </section>
  );
}
