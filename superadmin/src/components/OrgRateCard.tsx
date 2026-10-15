/** A university / organisation's own rate card: standard services chosen for it, at its own rates. */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Plus, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Badge, Loading, Modal, Panel, useConfirm, useToast } from '@/components/ui';
import { money, type RateServiceRow } from '@/pages/RateCards';

interface CardItem {
  id: number; service_id: number; name: string; description: string; unit_label: string; currency: string;
  tax_percent: number; standard_rate: number; rate: number; difference: number; service_active: boolean; notes: string;
}
interface Card { items: CardItem[]; available: RateServiceRow[] }

export function OrgRateCard({ orgId, orgName }: { orgId: number; orgName: string }) {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const key = ['admin', 'rates', 'card', orgId];
  const q = useQuery({ queryKey: key, queryFn: async () => (await api.get<Card>(`/api/superadmin/rates/organisations/${orgId}`)).data });
  const [adding, setAdding] = useState(false);
  const [picked, setPicked] = useState<Record<number, string>>({});  // service id -> rate
  const [edit, setEdit] = useState<{ id: number; rate: string } | null>(null);

  const done = (data: Card & { message: string }) => {
    toast.success(data.message);
    qc.setQueryData(key, data);
    void qc.invalidateQueries({ queryKey: ['admin', 'rates', 'services'] });
  };
  const add = async () => {
    try {
      const items = Object.entries(picked).map(([id, rate]) => ({ service_id: Number(id), rate: rate === '' ? null : rate }));
      const { data } = await api.post(`/api/superadmin/rates/organisations/${orgId}/items`, { items });
      done(data); setAdding(false); setPicked({});
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const saveRate = async () => {
    if (!edit) return;
    try {
      const { data } = await api.put(`/api/superadmin/rates/organisations/${orgId}/items/${edit.id}`, { rate: edit.rate });
      done(data); setEdit(null);
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const remove = async (i: CardItem) => {
    if (!(await confirm({ title: 'Remove from rate card', danger: true, confirmLabel: 'Remove',
      message: `Remove ${i.name} from ${orgName}'s rate card?` }))) return;
    try { done((await api.delete(`/api/superadmin/rates/organisations/${orgId}/items/${i.id}`)).data); }
    catch (err) { toast.error(errorMessage(err)); }
  };

  if (q.isLoading) return <Panel title="Rate card"><Loading /></Panel>;
  if (!q.data) return null;
  const { items, available } = q.data;

  return (
    <Panel title={`${orgName} rate card`} flush
      actions={<button className="btn btn-secondary btn-sm" onClick={() => setAdding(true)}><Plus size={13} /> Add services</button>}>
      {items.length === 0 ? (
        <div className="panel-body rc-empty">
          <div>
            <strong>No rate card yet</strong>
            <div className="small muted">Pick services from the <Link className="act" to="/rate-cards/">standard rate card</Link> and set {orgName}'s rates.</div>
          </div>
          <button className="btn btn-primary" onClick={() => setAdding(true)}><Plus size={14} /> Add services</button>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr><th>Service</th><th>Unit</th><th className="num">Standard</th><th className="num">{orgName} rate</th>
              <th className="num">Difference</th><th className="num">Tax</th><th /></tr></thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td><strong>{i.name}</strong>{!i.service_active && <Badge>Inactive service</Badge>}
                    {i.notes && <span className="tiny faint" style={{ display: 'block' }}>{i.notes}</span>}</td>
                  <td className="small">{i.unit_label || <span className="faint">—</span>}</td>
                  <td className="num faint">{money(i.standard_rate, i.currency)}</td>
                  <td className="num">
                    {edit?.id === i.id ? (
                      <span className="rc-edit">
                        <input className="input" type="number" min="0" step="0.01" autoFocus value={edit.rate}
                          onChange={(e) => setEdit({ id: i.id, rate: e.target.value })}
                          onKeyDown={(e) => { if (e.key === 'Enter') void saveRate(); if (e.key === 'Escape') setEdit(null); }} />
                        <button className="btn btn-ghost btn-icon" title="Save" onClick={saveRate}><Check size={14} /></button>
                        <button className="btn btn-ghost btn-icon" title="Cancel" onClick={() => setEdit(null)}><X size={14} /></button>
                      </span>
                    ) : (
                      <button className="act rc-rate" title="Change rate" onClick={() => setEdit({ id: i.id, rate: String(i.rate) })}>
                        <strong>{money(i.rate, i.currency)}</strong></button>
                    )}
                  </td>
                  <td className="num">{i.difference === 0 ? <span className="faint">Standard</span>
                    : <span className={i.difference < 0 ? 'rc-less' : 'rc-more'}>{i.difference > 0 ? '+' : '−'}{money(Math.abs(i.difference), i.currency)}</span>}</td>
                  <td className="num">{i.tax_percent}%</td>
                  <td><button className="btn btn-ghost btn-sm" onClick={() => remove(i)}><X size={13} /> Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={adding} onClose={() => setAdding(false)} title={`Add services to ${orgName}'s rate card`}
        footer={<>
          <button className="btn btn-secondary" onClick={() => setAdding(false)}>Cancel</button>
          <button className="btn btn-primary" disabled={!Object.keys(picked).length} onClick={add}>
            Add {Object.keys(picked).length || ''} service{Object.keys(picked).length === 1 ? '' : 's'}</button>
        </>}>
        {available.length === 0 ? (
          <p className="muted">Every active standard service is already on this card. To offer something new, add it to the{' '}
            <Link className="act" to="/rate-cards/">standard rate card</Link> first.</p>
        ) : (
          <>
            <p className="small muted" style={{ marginTop: 0 }}>Tick the services and set {orgName}'s rate (leave empty for the standard rate).
              A service that is not listed must be added to the <Link className="act" to="/rate-cards/">standard rate card</Link> first.</p>
            <table className="tbl">
              <thead><tr><th /><th>Service</th><th className="num">Standard</th><th className="num">Rate</th></tr></thead>
              <tbody>
                {available.map((s) => {
                  const on = s.id in picked;
                  return (
                    <tr key={s.id}>
                      <td><input type="checkbox" checked={on} aria-label={`Add ${s.name}`}
                        onChange={(e) => setPicked((p) => { const n = { ...p }; if (e.target.checked) n[s.id] = ''; else delete n[s.id]; return n; })} /></td>
                      <td><strong>{s.name}</strong>{s.unit_label && <span className="tiny faint" style={{ display: 'block' }}>{s.unit_label}</span>}</td>
                      <td className="num faint">{money(s.standard_rate, s.currency)}</td>
                      <td className="num"><input className="input rc-input" type="number" min="0" step="0.01" disabled={!on}
                        placeholder={String(s.standard_rate)} value={picked[s.id] ?? ''}
                        onChange={(e) => setPicked((p) => ({ ...p, [s.id]: e.target.value }))} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </Modal>
    </Panel>
  );
}
