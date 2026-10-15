/** Invoices across every university / organisation: approve or adjust them before they go to the client. */
import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Download, Pencil, X } from 'lucide-react';
import { api, downloadFile, errorMessage } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { Badge, ErrorNotice, Field, Loading, Modal, PageHeader, Panel, Spinner, Tabs, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';
import { money } from '@/pages/RateCards';
import { FinanceAnalytics } from '@/components/FinanceAnalytics';
import { FinanceReports } from '@/components/FinanceReports';

type Status = 'pending_turacoz' | 'pending_client' | 'awaiting_payment' | 'paid' | 'rejected';
interface Row {
  id: number; number: string; organisation_id: number; organisation: string; cycle: string; cycle_label: string; status: Status;
  status_label: string; total: number; period_start: string | null; period_end: string | null; created_at: string | null;
}
interface Line { id: number; description: string; sac_code: string; unit_label: string; quantity: number; rate: number; amount: number; tax_percent: number; cgst: number; sgst: number; igst: number }
interface Detail extends Row {
  tax_mode: string; tax_mode_label: string; subtotal: number; cgst: number; sgst: number; igst: number; amount_in_words: string;
  buyer: Record<string, string>; client_remarks: string; turacoz_remarks: string; lines: Line[];
  requests: { id: number; requested_by: string; document: string | null; document_number: string | null; requirement: string; created_at: string | null }[];
  events: { action: string; note: string; by: string; at: string | null }[];
}
interface Waiting { organisation_id: number; organisation: string; requests: number; billing_cycle: string; missing: string[] }

const TONE: Record<Status, 'ok' | 'warn' | 'danger' | 'accent'> = {
  pending_turacoz: 'warn', pending_client: 'accent', awaiting_payment: 'warn', paid: 'ok', rejected: 'danger',
};
const LABEL: Record<Status, string> = {
  pending_turacoz: 'To approve', pending_client: 'With client', awaiting_payment: 'Awaiting payment', paid: 'Paid', rejected: 'Cancelled',
};
const EVENTS: Record<string, string> = {
  created: 'Invoice generated', adjusted: 'Adjusted by Turacoz', turacoz_approved: 'Approved by Turacoz', cancelled: 'Cancelled',
  client_approved: 'Approved by the client', client_query: 'Query from the client', paid: 'Payment received',
};

export function InvoicesList() {
  const [params, setParams] = useSearchParams();
  // opens on Analytics; links with a status / workspace filter (or ?view=list) open the invoice list
  const view = (params.get('view') ?? (params.get('status') || params.get('organisation') ? 'list' : 'analytics')) as 'list' | 'analytics' | 'reports';
  const status = (params.get('status') ?? 'pending_turacoz') as Status | '';
  const org = params.get('organisation') ?? '';
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ['admin', 'invoices', status, org],
    queryFn: async () => (await api.get<{ invoices: Row[]; counts: Partial<Record<Status, number>>; waiting: Waiting[] }>(
      '/api/billing/invoices', { params: { status, organisation: org || undefined } })).data,
    placeholderData: (prev) => prev, enabled: view === 'list',
  });
  const viewTabs = (
    <div className="inv-tabs" style={{ margin: '0 0 20px' }}>
      <Tabs<'list' | 'analytics' | 'reports'> value={view} onChange={(v) => setParams(v === 'analytics' ? {} : { view: v })} tabs={[
        { value: 'analytics', label: 'Analytics' }, { value: 'list', label: 'Invoices' }, { value: 'reports', label: 'Reports' },
      ]} />
    </div>
  );
  if (view !== 'list') {
    return (
      <>
        <Crumbs items={[{ label: 'Invoices' }, { label: view === 'analytics' ? 'Analytics' : 'Reports' }]} />
        <PageHeader title="Invoices" subtitle="Finance across every university and organisation." />
        {viewTabs}
        {view === 'analytics' ? <FinanceAnalytics /> : <FinanceReports />}
      </>
    );
  }
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const n = (s: Status) => q.data.counts[s] ?? 0;
  const setStatus = (s: Status | '') => setParams({ view: 'list', ...(s !== 'pending_turacoz' ? { status: s } : {}), ...(org ? { organisation: org } : {}) });
  return (
    <>
      <Crumbs items={[{ label: 'Invoices' }]} />
      <PageHeader title="Invoices" subtitle="Generated from the services members request. Check and approve them; the university administrator then approves and pays." />
      {viewTabs}
      {q.data.waiting.length > 0 && (
        <Panel title="Requests not invoiced yet" flush>
          <table className="tbl">
            <thead><tr><th>Workspace</th><th className="num">Requests</th><th>Why</th></tr></thead>
            <tbody>{q.data.waiting.map((w) => (
              <tr key={w.organisation_id}>
                <td><Link className="act" to={`/organisations/${w.organisation_id}/`}>{w.organisation}</Link></td>
                <td className="num">{w.requests}</td>
                <td className="small">{w.missing.length ? <Badge tone="danger">Billing profile incomplete ({w.missing.join(', ')})</Badge>
                  : w.billing_cycle === 'monthly' ? 'Monthly billing — generate from the workspace Overview' : 'Waiting'}</td>
              </tr>))}</tbody>
          </table>
        </Panel>
      )}
      <div style={{ margin: '20px 0 0' }}>
        <Tabs<Status | ''> value={status} onChange={setStatus} tabs={[
          { value: 'pending_turacoz', label: `To approve (${n('pending_turacoz')})` },
          { value: 'pending_client', label: `With client (${n('pending_client')})` },
          { value: 'awaiting_payment', label: `Awaiting payment (${n('awaiting_payment')})` },
          { value: 'paid', label: `Paid (${n('paid')})` }, { value: 'rejected', label: 'Cancelled' }, { value: '', label: 'All' },
        ]} />
      </div>
      <section className="panel">
        {q.data.invoices.length === 0 ? <div className="panel-body muted">No invoices here.</div> : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>Invoice</th><th>Workspace</th><th>Date</th><th>Billing</th><th className="num">Total</th><th>Status</th></tr></thead>
              <tbody>{q.data.invoices.map((i) => (
                <tr key={i.id} className="clickable" onClick={() => navigate(`/invoices/${i.id}/`)}>
                  <td className="mono"><Link className="act" to={`/invoices/${i.id}/`} onClick={(e) => e.stopPropagation()}>{i.number}</Link></td>
                  <td>{i.organisation}</td>
                  <td className="small nowrap">{i.created_at ? formatDate(i.created_at) : ''}</td>
                  <td className="small">{i.cycle_label}</td>
                  <td className="num"><strong>{money(i.total)}</strong></td>
                  <td><Badge tone={TONE[i.status]}>{LABEL[i.status]}</Badge></td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export function InvoiceDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const key = ['admin', 'invoice', id];
  const q = useQuery({ queryKey: key, queryFn: async () => (await api.get<Detail>(`/api/billing/invoices/${id}`)).data });
  const [editing, setEditing] = useState(false);
  const [edits, setEdits] = useState<Record<number, { quantity: string; rate: string }>>({});
  const [dialog, setDialog] = useState<null | 'approve' | 'reject' | 'mark-paid'>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const inv = q.data;
  const intra = inv.tax_mode === 'intra';
  const canEdit = inv.status === 'pending_turacoz';
  const val = (l: Line, k: 'quantity' | 'rate') => edits[l.id]?.[k] ?? String(l[k]);
  const setVal = (l: Line, k: 'quantity' | 'rate', v: string) =>
    setEdits((e) => ({ ...e, [l.id]: { ...(e[l.id] ?? { quantity: String(l.quantity), rate: String(l.rate) }), [k]: v } }));

  const act = async (path: string, body: object) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/api/billing/invoices/${inv.id}/${path}`, body);
      toast.success(data.message);
      qc.setQueryData(key, data.invoice);
      void qc.invalidateQueries({ queryKey: ['admin', 'invoices'] });
      setDialog(null); setNote(''); setEditing(false); setEdits({});
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };

  return (
    <>
      <Crumbs items={[{ label: 'Invoices', to: '/invoices/?view=list' }, { label: inv.number }]} />
      <PageHeader eyebrow={inv.organisation} title={inv.number}
        subtitle={<span className="row-tight wrap"><Badge tone={TONE[inv.status]}>{LABEL[inv.status]}</Badge>
          <span className="small muted">{inv.created_at ? formatDate(inv.created_at) : ''} · {inv.cycle_label} · {inv.tax_mode_label}</span></span>}
        actions={<div className="row-tight wrap">
          <button className="btn btn-secondary" onClick={() => downloadFile(`/api/billing/invoices/${inv.id}/pdf`, undefined, `${inv.number}.pdf`)}><Download size={14} /> PDF</button>
          {canEdit && <>
            <button className="btn btn-secondary" onClick={() => setDialog('reject')}><X size={14} /> Cancel invoice</button>
            <button className="btn btn-primary" onClick={() => setDialog('approve')}><Check size={14} /> Approve & send</button>
          </>}
          {inv.status === 'awaiting_payment' && <button className="btn btn-secondary" onClick={() => setDialog('mark-paid')}>Record payment</button>}
        </div>} />
      {inv.client_remarks && canEdit && <div className="panel panel-body" style={{ background: 'var(--warn-soft)', marginBottom: 20 }}><strong>Query from the client:</strong> {inv.client_remarks}</div>}
      {inv.status === 'rejected' && <div className="panel panel-body" style={{ marginBottom: 20 }}><strong>Cancelled:</strong> {inv.turacoz_remarks}</div>}

      <Panel title="Services" flush actions={canEdit && !editing ? <button className="btn btn-ghost btn-sm" onClick={() => setEditing(true)}><Pencil size={13} /> Adjust</button> : undefined}>
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr><th>Description</th><th>SAC</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amount</th><th className="num">Tax</th>
              {intra ? <><th className="num">CGST</th><th className="num">SGST</th></> : <th className="num">IGST</th>}</tr></thead>
            <tbody>{inv.lines.map((l) => (
              <tr key={l.id}>
                <td>{l.description}</td><td className="small mono">{l.sac_code || '—'}</td>
                <td className="num">{editing ? <input className="input rc-input" type="number" min="0.01" step="any" aria-label="Quantity" value={val(l, 'quantity')} onChange={(e) => setVal(l, 'quantity', e.target.value)} /> : l.quantity}</td>
                <td className="num">{editing ? <input className="input rc-input" type="number" min="0" step="0.01" aria-label="Rate" value={val(l, 'rate')} onChange={(e) => setVal(l, 'rate', e.target.value)} /> : money(l.rate)}</td>
                <td className="num">{money(l.amount)}</td><td className="num">{l.tax_percent}%</td>
                {intra ? <><td className="num">{money(l.cgst)}</td><td className="num">{money(l.sgst)}</td></> : <td className="num">{money(l.igst)}</td>}
              </tr>))}</tbody>
          </table>
        </div>
        <div className="panel-body" style={{ display: 'grid', justifyContent: 'end', gap: 4, textAlign: 'right' }}>
          <span className="small">Subtotal {money(inv.subtotal)}</span>
          {intra ? <span className="small">CGST {money(inv.cgst)} · SGST {money(inv.sgst)}</span> : <span className="small">IGST {money(inv.igst)}</span>}
          <strong>Total {money(inv.total)}</strong>
          <span className="tiny faint">{inv.amount_in_words}</span>
          {editing && <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(false); setEdits({}); }}>Discard changes</button>}
        </div>
      </Panel>

      <div className="grid-2 tm-grid" style={{ marginTop: 20 }}>
        <Panel title="Requests" flush>
          <table className="tbl"><thead><tr><th>Member</th><th>Document</th><th>Requirement</th></tr></thead>
            <tbody>{inv.requests.map((r) => (
              <tr key={r.id}><td>{r.requested_by}<span className="tiny faint" style={{ display: 'block' }}>{r.created_at ? formatDate(r.created_at) : ''}</span></td>
                <td>{r.document ?? '—'}<span className="tiny faint mono" style={{ display: 'block' }}>{r.document_number}</span></td>
                <td className="small" style={{ whiteSpace: 'pre-wrap' }}>{r.requirement || '—'}</td></tr>))}</tbody>
          </table>
        </Panel>
        <Panel title="History">
          {inv.events.map((e, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <strong className="small">{EVENTS[e.action] ?? e.action}</strong>
              <div className="tiny faint">{e.by} · {e.at ? formatDateTime(e.at) : ''}</div>
              {e.note && <div className="small">{e.note}</div>}
            </div>))}
          <div className="tiny faint">Billed to {inv.buyer.name}{inv.buyer.gstin && ` · GSTIN ${inv.buyer.gstin}`} · {[inv.buyer.state, inv.buyer.country].filter(Boolean).join(', ')}</div>
        </Panel>
      </div>

      <Modal open={dialog !== null} onClose={() => setDialog(null)}
        title={dialog === 'approve' ? 'Approve and send to the client' : dialog === 'reject' ? 'Cancel this invoice' : 'Record a payment'}
        footer={<>
          <button className="btn btn-secondary" onClick={() => setDialog(null)}>Close</button>
          <button className={`btn ${dialog === 'reject' ? 'btn-danger' : 'btn-primary'}`} disabled={busy} onClick={() => {
            if (dialog === 'approve') void act('approve', { remarks: note, lines: Object.entries(edits).map(([lid, e]) => ({ id: Number(lid), ...e })) });
            else if (dialog === 'reject') void act('reject', { reason: note });
            else void act('mark-paid', { reference: note });
          }}>{busy && <Spinner />} {dialog === 'approve' ? 'Approve & send' : dialog === 'reject' ? 'Cancel invoice' : 'Mark as paid'}</button>
        </>}>
        <Field label={dialog === 'approve' ? 'Note (optional)' : dialog === 'reject' ? 'Reason' : 'Payment reference (e.g. bank UTR)'} required={dialog !== 'approve'}>
          <textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </Modal>
    </>
  );
}
