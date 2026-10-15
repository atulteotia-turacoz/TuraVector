/** One invoice: lines, GST, history and the actions for whoever is looking (Turacoz approver or university admin). */
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, CreditCard, Download, MessageSquareWarning, Pencil, X } from 'lucide-react';
import { api, downloadFile, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatDate, formatDateTime } from '@/lib/format';
import { BackLink, Badge, ErrorNotice, Field, Loading, Modal, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import { EVENT_LABELS, STATUS_TONE, inr, invoiceBase, type Invoice } from './api';
import { payWithRazorpay } from './razorpay';
import './billing.css';

type Dialog = null | 'approve' | 'reject' | 'query' | 'client-approve' | 'mark-paid';

export default function InvoiceDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const approver = !!user?.is_invoice_approver;
  const base = invoiceBase(approver);
  const key = ['invoice', approver, id];
  const q = useQuery({ queryKey: key, queryFn: async () => (await api.get<Invoice>(`${base}/${id}`)).data });
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [edits, setEdits] = useState<Record<number, { quantity: string; rate: string }>>({});
  const [editing, setEditing] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} title="Invoice not found" />;
  const inv = q.data;
  const intra = inv.tax_mode === 'intra';
  const canEdit = approver && inv.status === 'pending_turacoz';

  const refresh = (data?: { invoice?: Invoice }) => {
    if (data?.invoice) qc.setQueryData(key, data.invoice);
    void qc.invalidateQueries({ queryKey: ['invoices'] });
    void qc.invalidateQueries({ queryKey: ['invoice'] });
  };
  const act = async (path: string, body: object, after?: () => void) => {
    setBusy(true);
    try {
      const { data } = await api.post(`${base}/${inv.id}/${path}`, body);
      toast.success(data.message);
      setDialog(null); setNote(''); setEditing(false); setEdits({});
      if (after) { after(); void qc.invalidateQueries({ queryKey: ['invoices'] }); } else refresh(data);
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  const approveTuracoz = () => act('approve', {
    remarks: note,
    lines: Object.entries(edits).map(([lid, e]) => ({ id: Number(lid), quantity: e.quantity, rate: e.rate })),
  });
  const pay = async () => {
    setBusy(true);
    try {
      const { data: order } = await api.post(`${base}/${inv.id}/pay`);
      const result = await payWithRazorpay(order);
      if (result) {
        const { data } = await api.post(`${base}/${inv.id}/pay/verify`, result);
        toast.success(data.message);
        refresh(data);
      }
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  const lineValue = (lid: number, k: 'quantity' | 'rate', fallback: number) => edits[lid]?.[k] ?? String(fallback);
  const setLine = (lid: number, k: 'quantity' | 'rate', v: string, line: { quantity: number; rate: number }) =>
    setEdits((e) => ({ ...e, [lid]: { ...(e[lid] ?? { quantity: String(line.quantity), rate: String(line.rate) }), [k]: v } }));
  const preview = inv.lines.reduce((t, l) => t + Number(lineValue(l.id, 'quantity', l.quantity)) * Number(lineValue(l.id, 'rate', l.rate)), 0);

  const actions = (
    <div className="row-tight wrap">
      <button className="btn btn-secondary" onClick={() => downloadFile(`${base}/${inv.id}/pdf`, undefined, `${inv.number}.pdf`)}><Download size={14} /> PDF</button>
      {canEdit && <>
        <button className="btn btn-secondary" onClick={() => setDialog('reject')}><X size={14} /> Cancel invoice</button>
        <button className="btn btn-primary" onClick={() => setDialog('approve')}><Check size={14} /> Approve & send</button>
      </>}
      {approver && inv.status === 'awaiting_payment' && <button className="btn btn-secondary" onClick={() => setDialog('mark-paid')}>Record payment</button>}
      {!approver && inv.status === 'pending_client' && <>
        <button className="btn btn-secondary" onClick={() => setDialog('query')}><MessageSquareWarning size={14} /> Raise a query</button>
        <button className="btn btn-primary" onClick={() => setDialog('client-approve')}><Check size={14} /> Approve</button>
      </>}
      {!approver && inv.status === 'awaiting_payment' && (
        <button className="btn btn-primary" disabled={busy} onClick={pay}>{busy ? <Spinner /> : <CreditCard size={14} />} Pay {inr(inv.total)}</button>
      )}
    </div>
  );

  return (
    <>
      <BackLink to="/content-lab-management/invoices/">Invoices</BackLink>
      <PageHeader eyebrow={approver ? inv.organisation : 'Invoice'} title={inv.number}
        subtitle={<span className="row-tight wrap"><Badge tone={STATUS_TONE[inv.status]}>{inv.status_label}</Badge>
          <span className="small muted">{inv.created_at ? formatDate(inv.created_at) : ''} · {inv.cycle === 'monthly' && inv.period_start
            ? `Monthly, ${formatDate(inv.period_start)} – ${formatDate(inv.period_end)}` : 'Per submission'} · {inv.tax_mode_label}</span></span>}
        actions={actions} />

      {inv.client_remarks && inv.status === 'pending_turacoz' && (
        <div className="inv-note inv-note-warn"><strong>Query from {inv.organisation}:</strong> {inv.client_remarks}</div>
      )}
      {inv.status === 'rejected' && <div className="inv-note inv-note-warn"><strong>Cancelled:</strong> {inv.turacoz_remarks}</div>}

      <div className="inv-grid">
        <div className="stack-lg">
          <Panel title="Services" flush actions={canEdit && !editing
            ? <button className="btn btn-ghost btn-sm" onClick={() => setEditing(true)}><Pencil size={13} /> Adjust quantities / rates</button> : undefined}>
            <div className="table-scroll">
              <table className="tbl inv-lines">
                <thead><tr><th>Description</th><th>SAC</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amount</th>
                  <th className="num">Tax</th>{intra ? <><th className="num">CGST</th><th className="num">SGST</th></> : <th className="num">IGST</th>}</tr></thead>
                <tbody>
                  {inv.lines.map((l) => (
                    <tr key={l.id}>
                      <td>{l.description}</td>
                      <td className="small mono">{l.sac_code || '—'}</td>
                      <td className="num">{editing ? <input className="input inv-num" type="number" min="0.01" step="any" aria-label="Quantity"
                        value={lineValue(l.id, 'quantity', l.quantity)} onChange={(e) => setLine(l.id, 'quantity', e.target.value, l)} />
                        : <>{l.quantity}{l.unit_label && l.unit_label !== 'Fixed' && <div className="tiny faint">{l.unit_label.replace('Per ', '')}{l.quantity === 1 ? '' : 's'}</div>}</>}</td>
                      <td className="num">{editing ? <input className="input inv-num" type="number" min="0" step="0.01" aria-label="Rate"
                        value={lineValue(l.id, 'rate', l.rate)} onChange={(e) => setLine(l.id, 'rate', e.target.value, l)} /> : inr(l.rate)}</td>
                      <td className="num">{inr(l.amount)}</td>
                      <td className="num small">{l.tax_percent}%</td>
                      {intra ? <><td className="num small">{inr(l.cgst)}</td><td className="num small">{inr(l.sgst)}</td></> : <td className="num small">{inr(l.igst)}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {editing && (
              <div className="panel-body row-tight" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">New subtotal {inr(preview)} (tax is recalculated when you approve)</span>
                <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(false); setEdits({}); }}>Discard changes</button>
              </div>
            )}
            <div className="inv-totals">
              <div><span>Subtotal</span><span>{inr(inv.subtotal)}</span></div>
              {intra ? <>
                <div><span>CGST</span><span>{inr(inv.cgst)}</span></div>
                <div><span>SGST</span><span>{inr(inv.sgst)}</span></div>
              </> : <div><span>IGST{inv.tax_mode === 'overseas' ? ' (overseas)' : ''}</span><span>{inr(inv.igst)}</span></div>}
              <div className="inv-total"><span>Total</span><span>{inr(inv.total)}</span></div>
              <div className="tiny faint">{inv.amount_in_words}</div>
            </div>
          </Panel>

          <Panel title={`Requested by (${inv.requests.length})`} flush>
            <table className="tbl">
              <thead><tr><th>Member</th><th>Document</th><th>Requirement</th><th>Date</th></tr></thead>
              <tbody>
                {inv.requests.map((r) => (
                  <tr key={r.id}>
                    <td>{r.requested_by}</td>
                    <td>{r.document_id ? <Link className="act" to={`/content-lab-management/document/${r.document_id}/`}>{r.document}</Link> : '—'}
                      {r.document_number && <div className="tiny faint mono">{r.document_number}</div>}</td>
                    <td className="small inv-req">{r.requirement || <span className="faint">—</span>}</td>
                    <td className="small nowrap">{r.created_at ? formatDate(r.created_at) : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>

        <div className="stack-lg">
          <Panel title="Billed to">
            <div className="inv-party">
              <strong>{inv.buyer.name}</strong>
              {inv.buyer.address && <div>{inv.buyer.address}</div>}
              <div>{[inv.buyer.state, inv.buyer.country].filter(Boolean).join(', ')}</div>
              {inv.buyer.gstin && <div className="small">GSTIN {inv.buyer.gstin}</div>}
            </div>
            <div className="inv-party" style={{ marginTop: 14 }}>
              <span className="tiny faint">FROM</span>
              <strong>{inv.seller.company_name}</strong>
              <div className="small">{[inv.seller.state, inv.seller.country].filter(Boolean).join(', ')}{inv.seller.gstin && ` · GSTIN ${inv.seller.gstin}`}</div>
            </div>
          </Panel>
          <Panel title="History">
            <ol className="inv-timeline">
              {inv.events.map((e, i) => (
                <li key={i}>
                  <strong>{EVENT_LABELS[e.action] ?? e.action}</strong>
                  <div className="tiny faint">{e.by} · {e.at ? formatDateTime(e.at) : ''}</div>
                  {e.note && <div className="small">{e.note}</div>}
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>

      <Modal open={dialog !== null} onClose={() => setDialog(null)}
        title={{ approve: 'Approve and send to the client', reject: 'Cancel this invoice', query: 'Raise a query with Turacoz',
          'client-approve': 'Approve this invoice', 'mark-paid': 'Record a payment' }[dialog ?? 'approve']}
        footer={<>
          <button className="btn btn-secondary" onClick={() => setDialog(null)}>Close</button>
          <button className={`btn ${dialog === 'reject' ? 'btn-danger' : 'btn-primary'}`} disabled={busy} onClick={() => {
            if (dialog === 'approve') void approveTuracoz();
            else if (dialog === 'reject') void act('reject', { reason: note });
            else if (dialog === 'query') void act('query', { remarks: note }, () => navigate('/content-lab-management/invoices/'));
            else if (dialog === 'client-approve') void act('approve', { remarks: note });
            else if (dialog === 'mark-paid') void act('mark-paid', { reference: note });
          }}>{busy && <Spinner />} {{ approve: 'Approve & send', reject: 'Cancel invoice', query: 'Send query', 'client-approve': 'Approve', 'mark-paid': 'Mark as paid' }[dialog ?? 'approve']}</button>
        </>}>
        {dialog === 'approve' && <p className="small muted" style={{ marginTop: 0 }}>
          {inv.organisation}'s administrator is emailed and sees it on their dashboard.
          {Object.keys(edits).length > 0 && <> Your changes to {Object.keys(edits).length} line(s) are saved with it.</>}</p>}
        {dialog === 'client-approve' && <p className="small muted" style={{ marginTop: 0 }}>After you approve, you can pay {inr(inv.total)} online.</p>}
        <Field label={{ approve: 'Note (optional)', reject: 'Reason', query: 'What needs to change?', 'client-approve': 'Note (optional)', 'mark-paid': 'Payment reference (e.g. bank UTR)' }[dialog ?? 'approve']}
          required={dialog === 'reject' || dialog === 'query' || dialog === 'mark-paid'}>
          {dialog === 'mark-paid' ? <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
            : <textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
      </Modal>
    </>
  );
}
