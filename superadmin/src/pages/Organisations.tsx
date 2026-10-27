/** Organisations — university / organisation / individual workspaces: approve sign-ups, create workspaces. */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Building2, Check, Plus, Search, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Badge, ErrorNotice, Field, Loading, Modal, PageHeader, Spinner, Tabs, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

export interface OrgRow {
  id: number; name: string; kind: 'university' | 'organisation' | 'individual' | 'system'; website: string; logo_url: string | null;
  status: 'pending' | 'active' | 'rejected' | 'suspended'; slug: string; join_code: string | null; members: number;
  pending_requests: number; admins: string[]; created_at: string | null; approved_at: string | null;
  requested_plan?: string;
}

interface Resp { organisations: OrgRow[]; status_counts: Record<string, number> }

type StatusTab = '' | 'pending' | 'active' | 'suspended' | 'rejected';

export const STATUS_TONE: Record<OrgRow['status'], 'warn' | 'ok' | 'danger' | 'accent'> = {
  pending: 'warn', active: 'ok', suspended: 'danger', rejected: 'danger',
};

export function OrgLogo({ org, size = 32 }: { org: Pick<OrgRow, 'name' | 'logo_url'>; size?: number }) {
  return org.logo_url
    ? <img src={org.logo_url} alt="" style={{ width: size, height: size, objectFit: 'contain' }} />
    : <span className="org-initial" style={{ width: size, height: size }}>{org.name.slice(0, 1).toUpperCase()}</span>;
}

export default function Organisations() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [status, setStatus] = useState<StatusTab>('pending');
  const [kind, setKind] = useState('');
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [creating, setCreating] = useState(false);
  const q = useQuery({
    queryKey: ['admin', 'organisations', status, kind, term],
    queryFn: async () => (await api.get<Resp>('/api/superadmin/organisations', { params: { status, kind, q: term } })).data,
    placeholderData: (prev) => prev,
  });

  const decide = async (org: OrgRow, next: OrgRow['status']) => {
    const verb = next === 'active' ? 'Approve' : next === 'rejected' ? 'Reject' : 'Suspend';
    if (next !== 'active' && !(await confirm({ title: `${verb} ${org.name}`, danger: true, confirmLabel: verb,
      message: `Members of ${org.name} will not be able to sign in. The administrator is told by email.` }))) return;
    try {
      const { data } = await api.post(`/api/superadmin/organisations/${org.id}/status`, { status: next });
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'organisations'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;
  const c = d.status_counts;

  return (
    <>
      <Crumbs items={[{ label: 'Organisations' }]} />
      <PageHeader title="Organisations"
        subtitle="Workspaces of universities, organisations and individuals. Approve new sign-ups, create workspaces and choose their administrators."
        actions={<button className="btn btn-primary" onClick={() => setCreating(true)}><Plus size={15} /> New workspace</button>} />

      <section className="panel">
        <div className="panel-head org-head">
          <Tabs<StatusTab> value={status} onChange={setStatus} tabs={[
            { value: 'pending', label: `Awaiting approval (${c.pending ?? 0})` },
            { value: 'active', label: `Active (${c.active ?? 0})` },
            { value: 'suspended', label: `Suspended (${c.suspended ?? 0})` },
            { value: 'rejected', label: `Rejected (${c.rejected ?? 0})` },
            { value: '', label: 'All' },
          ]} />
          <div className="row-tight">
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Type">
              <option value="">All types</option><option value="university">Universities</option>
              <option value="organisation">Organisations</option><option value="individual">Individuals</option>
            </select>
            <form className="search-input" onSubmit={(e) => { e.preventDefault(); setTerm(search.trim()); }}>
              <Search size={14} />
              <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or website…" aria-label="Search organisations" />
            </form>
          </div>
        </div>
        {d.organisations.length === 0 ? (
          <div className="panel-body muted">No workspaces here.</div>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>Workspace</th><th>Type</th><th>Administrators</th><th>Members</th><th>Registered</th><th>Status</th><th /></tr></thead>
              <tbody>
                {d.organisations.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <Link to={`/organisations/${o.id}/`} className="org-cell">
                        <OrgLogo org={o} />
                        <span><strong>{o.name}</strong>{o.website && <span className="tiny faint" style={{ display: 'block' }}>{o.website}</span>}
                          {o.requested_plan && <span className="tiny" style={{ display: 'block' }}>Plan chosen: <strong>{o.requested_plan}</strong></span>}</span>
                      </Link>
                    </td>
                    <td className="cap">{o.kind}</td>
                    <td>{o.admins.length ? o.admins.join(', ') : <span className="faint">None yet</span>}</td>
                    <td>{o.members}{o.pending_requests > 0 && <span className="tiny faint"> · {o.pending_requests} waiting</span>}</td>
                    <td>{o.created_at ? formatDate(o.created_at) : ''}</td>
                    <td><Badge tone={STATUS_TONE[o.status]}>{o.status}</Badge></td>
                    <td><div className="row-tight" style={{ justifyContent: 'flex-end' }}>
                      {o.status === 'pending' && <>
                        <button className="btn btn-primary btn-sm" onClick={() => decide(o, 'active')}><Check size={13} /> Approve</button>
                        <button className="btn btn-secondary btn-sm" onClick={() => decide(o, 'rejected')}><X size={13} /> Reject</button>
                      </>}
                      <Link to={`/organisations/${o.id}/`} className="btn btn-ghost btn-sm">Open</Link>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <CreateModal open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

function CreateModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const blank = { name: '', kind: 'university', website: '', admin_username: '', admin_email: '', admin_first_name: '', admin_last_name: '', admin_password: '' };
  const [form, setForm] = useState(blank);
  const [logo, setLogo] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const fd = new FormData();
    Object.entries(form).forEach(([k, v]) => fd.append(k, v));
    if (logo) fd.append('logo', logo);
    try {
      const { data } = await api.post('/api/superadmin/organisations', fd);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin', 'organisations'] });
      setForm(blank);
      setLogo(null);
      onClose();
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  return (
    <Modal open={open} onClose={onClose} title={<span className="row-tight"><Building2 size={16} /> New workspace</span>}
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" form="org-create" disabled={busy}>{busy && <Spinner />} Create</button></>}>
      <form id="org-create" onSubmit={submit} className="form-grid">
        <Field label="Name" required><input className="input" required value={form.name} onChange={set('name')} /></Field>
        <Field label="Type">
          <select className="input" value={form.kind} onChange={set('kind')}>
            <option value="university">University</option><option value="organisation">Organisation</option><option value="individual">Individual</option>
          </select>
        </Field>
        <Field label="Website"><input className="input" type="url" value={form.website} onChange={set('website')} placeholder="https://" /></Field>
        <Field label="Logo" help="PNG or JPG, up to 2 MB."><input className="input" type="file" accept="image/png,image/jpeg" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} /></Field>
        <div className="span-2 faint small">Administrator account (optional — you can also make an existing user the administrator later)</div>
        <Field label="Username"><input className="input" value={form.admin_username} onChange={set('admin_username')} autoComplete="off" /></Field>
        <Field label="Email"><input className="input" type="email" value={form.admin_email} onChange={set('admin_email')} /></Field>
        <Field label="First name"><input className="input" value={form.admin_first_name} onChange={set('admin_first_name')} /></Field>
        <Field label="Last name"><input className="input" value={form.admin_last_name} onChange={set('admin_last_name')} /></Field>
        <Field label="Password" help="At least 8 characters."><input className="input" type="password" value={form.admin_password} onChange={set('admin_password')} autoComplete="new-password" /></Field>
      </form>
    </Modal>
  );
}
