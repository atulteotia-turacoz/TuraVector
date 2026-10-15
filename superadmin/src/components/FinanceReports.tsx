/** Finance reports (superadmin, every workspace): invoice register, GST summary, clients, services, outstanding and payments. */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Download, FileSpreadsheet, FileText } from 'lucide-react';
import { api, downloadFile, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Badge, ErrorNotice, Loading, Stat, Tabs, useToast } from '@/components/ui';
import { money as inr } from '@/pages/RateCards';

type InvoiceStatus = 'pending_turacoz' | 'pending_client' | 'awaiting_payment' | 'paid' | 'rejected';
const STATUS_TONE: Record<InvoiceStatus, 'ok' | 'warn' | 'danger' | 'accent'> = {
  pending_turacoz: 'warn', pending_client: 'accent', awaiting_payment: 'warn', paid: 'ok', rejected: 'danger',
};

interface Report {
  period: { from: string; to: string };
  summary: { invoices: number; subtotal: number; tax: number; total: number; received: number; outstanding: number; drafts: number; cancelled: number };
  register: { id: number; number: string; date: string; organisation: string; gstin: string; place: string; status: InvoiceStatus; status_label: string;
    subtotal: number; cgst: number; sgst: number; igst: number; total: number; paid_on: string | null; payment_ref: string }[];
  gst: { category: string; tax_mode: string; rate: number; invoices: number; taxable: number; cgst: number; sgst: number; igst: number; total_tax: number }[];
  by_organisation: { organisation: string; invoices: number; subtotal: number; tax: number; total: number; paid: number; outstanding: number }[];
  by_service: { service: string; sac_code: string; lines: number; quantity: number; amount: number }[];
  outstanding: { id: number; number: string; organisation: string; date: string; status_label: string; total: number; days: number; bucket: string; reminders_sent: number }[];
  payments: { number: string; organisation: string; paid_on: string; amount: number; reference: string; gateway: string }[];
  organisations: { id: number; name: string }[];
}
type Section = 'register' | 'gst' | 'by_organisation' | 'by_service' | 'outstanding' | 'payments';

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
function preset(p: string): [string, string] {
  const t = new Date();
  const fyStart = new Date(t.getMonth() >= 3 ? t.getFullYear() : t.getFullYear() - 1, 3, 1);
  switch (p) {
    case 'last_month': return [ymd(new Date(t.getFullYear(), t.getMonth() - 1, 1)), ymd(new Date(t.getFullYear(), t.getMonth(), 0))];
    case 'quarter': { const q = Math.floor(((t.getMonth() + 9) % 12) / 3); const s = new Date(fyStart.getFullYear(), 3 + q * 3, 1); return [ymd(s), ymd(t)]; }
    case 'fy': return [ymd(fyStart), ymd(t)];
    case 'last_fy': return [ymd(new Date(fyStart.getFullYear() - 1, 3, 1)), ymd(new Date(fyStart.getFullYear(), 2, 31))];
    default: return [ymd(new Date(t.getFullYear(), t.getMonth(), 1)), ymd(t)];
  }
}
const PRESETS = [{ v: 'month', l: 'This month' }, { v: 'last_month', l: 'Last month' }, { v: 'quarter', l: 'This quarter (FY)' },
  { v: 'fy', l: 'This financial year' }, { v: 'last_fy', l: 'Last financial year' }, { v: 'custom', l: 'Custom range…' }];

export function FinanceReports() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const range = params.get('range') ?? 'month';
  const [defFrom, defTo] = preset(range);
  const from = range === 'custom' ? params.get('from') ?? defFrom : defFrom;
  const to = range === 'custom' ? params.get('to') ?? defTo : defTo;
  const organisation = params.get('r_org') ?? '';
  const status = params.get('r_status') ?? '';
  const [draft, setDraft] = useState({ from, to });
  const [section, setSection] = useState<Section>('register');
  const query = { date_from: from, date_to: to, organisation: organisation || undefined, status: status || undefined };
  const q = useQuery({
    queryKey: ['admin', 'invoices', 'reports', query], placeholderData: (prev) => prev,
    queryFn: async () => (await api.get<Report>('/api/billing/reports', { params: query })).data,
  });
  const update = (next: Record<string, string>) => {
    const p = new URLSearchParams(params);
    Object.entries(next).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)));
    setParams(p, { replace: true });
  };
  const download = async (format: 'xlsx' | 'pdf' | 'csv') => {
    try {
      await downloadFile('/api/billing/reports/export', { ...query, format, section: format === 'csv' ? section : undefined },
        `turavector_finance_${from}_to_${to}.${format}`);
    } catch (err) { toast.error(errorMessage(err)); }
  };

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const r = q.data;
  const s = r.summary;
  const counts: Record<Section, number> = { register: r.register.length, gst: r.gst.length, by_organisation: r.by_organisation.length,
    by_service: r.by_service.length, outstanding: r.outstanding.length, payments: r.payments.length };

  return (
    <>
      <div className="row-tight fr-actions">
        <span className="small muted grow">Invoices dated in the period; payments received in it. Outstanding is as of today.</span>
        <button className="btn btn-secondary btn-sm" onClick={() => download('xlsx')}><FileSpreadsheet size={14} /> Excel</button>
        <button className="btn btn-secondary btn-sm" onClick={() => download('pdf')}><FileText size={14} /> PDF</button>
      </div>

      <section className="panel fr-filters">
        <label className="field"><span className="field-label">Period</span>
          <select className="input" value={range} onChange={(e) => { const v = e.target.value; if (v === 'custom') { setDraft({ from, to }); update({ range: v, from, to }); } else update({ range: v, from: '', to: '' }); }}>
            {PRESETS.map((p) => <option key={p.v} value={p.v}>{p.l}</option>)}
          </select></label>
        {range === 'custom' ? (
          <div className="fr-custom">
            <label className="field"><span className="field-label">From</span><input className="input" type="date" value={draft.from} max={draft.to} onChange={(e) => setDraft((d) => ({ ...d, from: e.target.value }))} /></label>
            <label className="field"><span className="field-label">To</span><input className="input" type="date" value={draft.to} min={draft.from} onChange={(e) => setDraft((d) => ({ ...d, to: e.target.value }))} /></label>
            <button className="btn btn-primary" disabled={!draft.from || !draft.to || draft.to < draft.from} onClick={() => update({ from: draft.from, to: draft.to })}>Apply</button>
          </div>
        ) : <div className="small muted fr-range">{formatDate(from)} – {formatDate(to)}</div>}
        <label className="field"><span className="field-label">University / organisation</span>
          <select className="input" value={organisation} onChange={(e) => update({ r_org: e.target.value })}>
            <option value="">All ({r.organisations.length})</option>
            {r.organisations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select></label>
        <label className="field"><span className="field-label">Status</span>
          <select className="input" value={status} onChange={(e) => update({ r_status: e.target.value })}>
            <option value="">All</option><option value="pending_turacoz">Awaiting Turacoz</option><option value="pending_client">With client</option>
            <option value="awaiting_payment">Awaiting payment</option><option value="paid">Paid</option><option value="rejected">Cancelled</option>
          </select></label>
      </section>

      <div className="stat-grid" style={{ margin: '20px 0' }}>
        <Stat value={inr(s.total)} label="Billed" note={`${s.invoices} invoice${s.invoices === 1 ? '' : 's'} · taxable ${inr(s.subtotal)}`} />
        <Stat value={inr(s.tax)} label="GST" />
        <Stat value={inr(s.received)} label="Received" note={`${r.payments.length} payment${r.payments.length === 1 ? '' : 's'}`} />
        <Stat value={inr(s.outstanding)} label="Outstanding" note={`${r.outstanding.length} invoice${r.outstanding.length === 1 ? '' : 's'}`} />
        <Stat value={s.drafts} label="With Turacoz" note={s.cancelled ? `${s.cancelled} cancelled` : 'Not yet billed'} />
      </div>

      <div className="inv-tabs"><Tabs<Section> value={section} onChange={setSection} tabs={[
        { value: 'register', label: `Invoice register (${counts.register})` }, { value: 'gst', label: 'GST summary' },
        { value: 'by_organisation', label: 'By client' }, { value: 'by_service', label: 'By service' },
        { value: 'outstanding', label: `Outstanding (${counts.outstanding})` }, { value: 'payments', label: `Payments (${counts.payments})` },
      ]} /></div>
      <section className="panel">
        <div className="panel-head"><span className="small muted">{counts[section]} row{counts[section] === 1 ? '' : 's'}</span>
          <button className="btn btn-ghost btn-sm" disabled={!counts[section]} onClick={() => download('csv')}><Download size={13} /> CSV</button></div>
        {counts[section] === 0 ? <div className="panel-body muted">Nothing in this period.</div> : (
          <div className="table-scroll">
            <table className="tbl">
              {section === 'register' && <>
                <thead><tr><th>Invoice</th><th>Date</th><th>Client</th><th>Status</th><th className="num">Taxable</th><th className="num">CGST</th><th className="num">SGST</th><th className="num">IGST</th><th className="num">Total</th><th>Paid on</th></tr></thead>
                <tbody>{r.register.map((x) => (
                  <tr key={x.id}><td className="mono"><Link className="act" to={`/invoices/${x.id}/`}>{x.number}</Link></td>
                    <td className="small nowrap">{formatDate(x.date)}</td><td>{x.organisation}{x.gstin && <div className="tiny faint">GSTIN {x.gstin}</div>}</td>
                    <td><Badge tone={STATUS_TONE[x.status]}>{x.status_label}</Badge></td>
                    <td className="num">{inr(x.subtotal)}</td><td className="num">{inr(x.cgst)}</td><td className="num">{inr(x.sgst)}</td><td className="num">{inr(x.igst)}</td>
                    <td className="num"><strong>{inr(x.total)}</strong></td><td className="small nowrap">{x.paid_on ? formatDate(x.paid_on) : '—'}</td></tr>))}</tbody>
              </>}
              {section === 'gst' && <>
                <thead><tr><th>Category</th><th>Supply</th><th className="num">Rate</th><th className="num">Invoices</th><th className="num">Taxable value</th><th className="num">CGST</th><th className="num">SGST</th><th className="num">IGST</th><th className="num">Total tax</th></tr></thead>
                <tbody>{r.gst.map((x, i) => (
                  <tr key={i}><td>{x.category}</td><td>{{ intra: 'Intra-state', inter: 'Inter-state', overseas: 'Overseas' }[x.tax_mode]}</td><td className="num">{x.rate}%</td><td className="num">{x.invoices}</td>
                    <td className="num">{inr(x.taxable)}</td><td className="num">{inr(x.cgst)}</td><td className="num">{inr(x.sgst)}</td><td className="num">{inr(x.igst)}</td><td className="num"><strong>{inr(x.total_tax)}</strong></td></tr>))}</tbody>
              </>}
              {section === 'by_organisation' && <>
                <thead><tr><th>Client</th><th className="num">Invoices</th><th className="num">Taxable</th><th className="num">GST</th><th className="num">Total</th><th className="num">Paid</th><th className="num">Outstanding</th></tr></thead>
                <tbody>{r.by_organisation.map((x) => (
                  <tr key={x.organisation}><td>{x.organisation}</td><td className="num">{x.invoices}</td><td className="num">{inr(x.subtotal)}</td><td className="num">{inr(x.tax)}</td>
                    <td className="num"><strong>{inr(x.total)}</strong></td><td className="num">{inr(x.paid)}</td><td className="num">{inr(x.outstanding)}</td></tr>))}</tbody>
              </>}
              {section === 'by_service' && <>
                <thead><tr><th>Service</th><th>SAC</th><th className="num">Lines</th><th className="num">Quantity</th><th className="num">Amount (taxable)</th></tr></thead>
                <tbody>{r.by_service.map((x) => (
                  <tr key={x.service}><td>{x.service}</td><td className="mono small">{x.sac_code || '—'}</td><td className="num">{x.lines}</td><td className="num">{x.quantity}</td><td className="num"><strong>{inr(x.amount)}</strong></td></tr>))}</tbody>
              </>}
              {section === 'outstanding' && <>
                <thead><tr><th>Invoice</th><th>Client</th><th>Date</th><th>Status</th><th className="num">Amount</th><th className="num">Days</th><th>Ageing</th><th className="num">Reminders</th></tr></thead>
                <tbody>{r.outstanding.map((x) => (
                  <tr key={x.id}><td className="mono"><Link className="act" to={`/invoices/${x.id}/`}>{x.number}</Link></td><td>{x.organisation}</td>
                    <td className="small nowrap">{formatDate(x.date)}</td><td className="small">{x.status_label}</td><td className="num"><strong>{inr(x.total)}</strong></td>
                    <td className="num">{x.days}</td><td>{x.days > 30 ? <Badge tone="danger">{x.bucket}</Badge> : x.bucket}</td><td className="num">{x.reminders_sent}</td></tr>))}</tbody>
              </>}
              {section === 'payments' && <>
                <thead><tr><th>Invoice</th><th>Client</th><th>Paid on</th><th className="num">Amount</th><th>Reference</th><th>Through</th></tr></thead>
                <tbody>{r.payments.map((x) => (
                  <tr key={x.number}><td className="mono">{x.number}</td><td>{x.organisation}</td><td className="small nowrap">{formatDate(x.paid_on)}</td>
                    <td className="num"><strong>{inr(x.amount)}</strong></td><td className="mono small">{x.reference}</td><td className="small cap">{x.gateway}</td></tr>))}</tbody>
              </>}
            </table>
          </div>
        )}
      </section>
    </>
  );
}
