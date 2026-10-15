/** University / organisation admin console: members, join requests, adding members, bulk import, settings. */
import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Download, KeyRound, RefreshCw, Shield, Upload, UserPlus, X } from 'lucide-react';
import { api, downloadFile, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatDate, timeAgo } from '@/lib/format';
import {
  Badge, DataTable, Empty, ErrorNotice, Field, Loading, PageHeader, Panel, SearchSelect, Spinner, Stat, Tabs, useConfirm, useToast,
  type Column,
} from '@/components/ui';
import './organisation.css';

interface Overview {
  organisation: { id: number; name: string; kind: string; website: string; logo_url: string | null; join_code: string | null };
  members: number;
  pending_requests: number;
  documents: number;
  references: number;
  member_user_types: { value: string; label: string }[];
}

interface Member {
  user_id: number; username: string; email: string; first_name: string; last_name: string; user_type_display: string;
  role: 'admin' | 'member'; status: string; is_active: boolean; date_joined: string | null; last_login: string | null;
  documents: number; requested_at: string | null; is_poc: boolean; designation: string;
}

type Tab = 'members' | 'requests' | 'reviewers' | 'pocs' | 'billing' | 'add' | 'import' | 'settings';

export default function OrganisationPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab | null) ?? 'members';
  const setTab = (t: Tab) => setParams(t === 'members' ? {} : { tab: t }, { replace: true });
  const overview = useQuery({
    queryKey: ['org', 'overview'],
    queryFn: async () => (await api.get('/api/org/overview')).data as Overview,
    enabled: !!user?.is_org_admin,
  });

  if (!user?.is_org_admin) {
    return <Empty title="Organisation administrators only">Only the administrator of a university or organisation workspace can open this page.</Empty>;
  }
  if (overview.isLoading) return <Loading />;
  if (overview.isError || !overview.data) return <ErrorNotice error={overview.error} />;
  const o = overview.data;
  const kind = o.organisation.kind === 'organisation' ? 'Organisation' : 'University';

  return (
    <>
      <PageHeader eyebrow={`${kind} workspace`} title={o.organisation.name}
        subtitle="Members, join requests and workspace settings. Reports, analytics and documents of your members are in the Dashboard and the Document Library."
        actions={<Link to="/content-lab-management/reports/" className="btn btn-secondary">Reports</Link>} />
      <div className="stat-grid org-stats">
        <Stat value={o.members} label="Members" />
        <Stat value={o.pending_requests} label="Join requests" note={o.pending_requests ? 'Waiting for you' : undefined} />
        <Stat value={o.documents} label="Documents" />
        <Stat value={o.references} label="References" />
      </div>
      <JoinCodePanel code={o.organisation.join_code} />
      <div className="org-tabs">
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[
          { value: 'members', label: 'Members' },
          { value: 'requests', label: <>Join requests{o.pending_requests > 0 && <span className="org-count">{o.pending_requests}</span>}</> },
          { value: 'reviewers', label: 'Reviewers' },
          { value: 'pocs', label: 'PoCs' },
          { value: 'billing', label: 'Billing' },
          { value: 'add', label: 'Add member' },
          { value: 'import', label: 'Bulk import' },
          { value: 'settings', label: 'Settings' },
        ]} />
      </div>
      {tab === 'members' && <MembersTab />}
      {tab === 'requests' && <RequestsTab />}
      {tab === 'add' && <AddMemberTab types={o.member_user_types} onDone={() => setTab('members')} />}
      {tab === 'import' && <ImportTab />}
      {tab === 'reviewers' && <ReviewersTab />}
      {tab === 'pocs' && <PocsTab />}
      {tab === 'billing' && <BillingTab />}
      {tab === 'settings' && <SettingsTab overview={o} />}
    </>
  );
}

function JoinCodePanel({ code }: { code: string | null }) {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  if (!code) return null;
  const link = `${window.location.origin}/signup/?type=join&code=${code}`;
  const copy = async (text: string, what: string) => {
    try { await navigator.clipboard.writeText(text); toast.success(`${what} copied`); } catch { toast.error('Could not copy'); }
  };
  const regenerate = async () => {
    if (!(await confirm({ title: 'New join code', message: 'The current code will stop working. Continue?', confirmLabel: 'Create new code' }))) return;
    try {
      const { data } = await api.post('/api/org/join-code/regenerate');
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['org'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };
  return (
    <div className="org-join">
      <div className="org-join-main">
        <KeyRound size={16} />
        <span>Students and researchers can join with code</span>
        <code className="org-code">{code}</code>
      </div>
      <div className="row-tight">
        <button className="btn btn-secondary btn-sm" onClick={() => copy(code, 'Code')}><Copy size={13} /> Copy code</button>
        <button className="btn btn-secondary btn-sm" onClick={() => copy(link, 'Sign-up link')}><Copy size={13} /> Copy sign-up link</button>
        <button className="btn btn-ghost btn-sm" onClick={regenerate}><RefreshCw size={13} /> New code</button>
      </div>
    </div>
  );
}

function useMembers(status: string) {
  return useQuery({
    queryKey: ['org', 'members', status],
    queryFn: async () => (await api.get('/api/org/members', { params: { status } })).data.members as Member[],
  });
}

function MembersTab() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = useMembers('active');
  const act = async (path: string, body?: unknown) => {
    try {
      const { data } = await api.post(path, body);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['org'] });
      return data;
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const resetPassword = async (m: Member) => {
    if (!(await confirm({ title: 'Reset password', message: `Create a new password for ${m.username}? Their current password stops working.`, confirmLabel: 'Reset' }))) return;
    const data = await act(`/api/org/members/${m.user_id}/reset-password`);
    if (data?.password) window.prompt(`New password for ${m.username} — share it with them securely:`, data.password);
  };
  const columns: Column<Member>[] = [
    { key: 'name', header: 'Member', value: (m) => `${m.first_name} ${m.last_name} ${m.username}`, render: (m) => (
      <div><div className="org-name">{`${m.first_name} ${m.last_name}`.trim() || m.username}</div><div className="tiny faint">{m.username} · {m.email}</div></div>
    ) },
    { key: 'user_type_display', header: 'Type' },
    { key: 'role', header: 'Role', render: (m) => (
      <span className="row-tight wrap">{m.role === 'admin' ? <Badge tone="accent">Admin</Badge> : <span className="muted">Member</span>}
        {m.is_poc && <Badge tone="ok">PoC</Badge>}</span>) },
    { key: 'documents', header: 'Documents', sortable: true },
    { key: 'last_login', header: 'Last sign-in', sortable: true, render: (m) => m.last_login ? timeAgo(m.last_login) : <span className="faint">Never</span> },
    { key: 'is_active', header: 'Status', value: (m) => (m.is_active ? 'active' : 'inactive'), render: (m) => m.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Inactive</Badge> },
    { key: 'actions', header: '', render: (m) => m.user_id === user?.id ? <span className="tiny faint">You</span> : (
      // actions work on their own; clicking elsewhere in the row opens the member
      <div className="row-tight org-actions org-actions-cell" onClick={(e) => e.stopPropagation()}>
        <button className="act" onClick={() => act(`/api/org/members/${m.user_id}/role`, { role: m.role === 'admin' ? 'member' : 'admin' })}>
          <Shield size={13} /> {m.role === 'admin' ? 'Remove admin' : 'Make admin'}</button>
        <button className="act" onClick={() => resetPassword(m)}><KeyRound size={13} /> Reset password</button>
        <button className="act" onClick={() => act(`/api/org/members/${m.user_id}/toggle-active`)}>{m.is_active ? 'Deactivate' : 'Activate'}</button>
      </div>
    ) },
  ];
  if (q.isLoading) return <Loading />;
  if (q.isError) return <ErrorNotice error={q.error} />;
  return (
    <Panel flush>
      <DataTable rows={q.data ?? []} columns={columns} rowKey={(m) => m.user_id} empty="No members yet."
        onRowClick={(m) => navigate(`/content-lab-management/organisation/members/${m.user_id}/`)} />
    </Panel>
  );
}

function RequestsTab() {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useMembers('pending');
  const decide = async (m: Member, action: 'approve' | 'reject') => {
    try {
      const { data } = await api.post(`/api/org/members/${m.user_id}/${action}`);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['org'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };
  if (q.isLoading) return <Loading />;
  if (q.isError) return <ErrorNotice error={q.error} />;
  if (!q.data?.length) return <Empty title="No pending requests">People who sign up with your join code appear here for approval.</Empty>;
  return (
    <Panel flush>
      <DataTable rows={q.data} rowKey={(m) => m.user_id} searchable={false} columns={[
        { key: 'name', header: 'Person', value: (m) => m.username, render: (m) => (
          <div><div className="org-name">{`${m.first_name} ${m.last_name}`.trim()}</div><div className="tiny faint">{m.username} · {m.email}</div></div>) },
        { key: 'user_type_display', header: 'Type' },
        { key: 'requested_at', header: 'Requested', render: (m) => (m.requested_at ? formatDate(m.requested_at) : '') },
        { key: 'actions', header: '', render: (m) => (
          <div className="row-tight">
            <button className="btn btn-primary btn-sm" onClick={() => decide(m, 'approve')}><Check size={13} /> Approve</button>
            <button className="btn btn-secondary btn-sm" onClick={() => decide(m, 'reject')}><X size={13} /> Reject</button>
          </div>) },
      ]} />
    </Panel>
  );
}

function AddMemberTab({ types, onDone }: { types: { value: string; label: string }[]; onDone: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const blank = { username: '', email: '', first_name: '', last_name: '', password: '', user_type: 'student', role: 'member', send_welcome_email: true };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ username: string; password: string } | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post('/api/org/members', form);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['org'] });
      if (data.password) setCreated({ username: form.username, password: data.password });
      else onDone();
      setForm(blank);
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  return (
    <Panel title="Add a student or researcher">
      {created && (
        <div className="notice notice-ok" style={{ marginBottom: 14 }}>
          Account <strong>{created.username}</strong> created with password <code>{created.password}</code>. Share it securely; they can change it after signing in.
        </div>
      )}
      <form onSubmit={submit} className="form-grid">
        <Field label="First name" required><input className="input" required value={form.first_name} onChange={set('first_name')} /></Field>
        <Field label="Last name"><input className="input" value={form.last_name} onChange={set('last_name')} /></Field>
        <Field label="Username" required><input className="input" required value={form.username} onChange={set('username')} autoComplete="off" /></Field>
        <Field label="Email" required><input className="input" type="email" required value={form.email} onChange={set('email')} /></Field>
        <Field label="Account type" required>
          <select className="input" value={form.user_type} onChange={set('user_type')}>{types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select>
        </Field>
        <Field label="Role in workspace">
          <select className="input" value={form.role} onChange={set('role')}><option value="member">Member</option><option value="admin">Administrator</option></select>
        </Field>
        <Field label="Password" help="Leave empty to generate one."><input className="input" type="password" minLength={8} value={form.password} onChange={set('password')} autoComplete="new-password" /></Field>
        <Field label=" ">
          <label className="check"><input type="checkbox" checked={form.send_welcome_email} onChange={(e) => setForm((f) => ({ ...f, send_welcome_email: e.target.checked }))} /> <span>Email the sign-in details</span></label>
        </Field>
        <div className="span-2"><button className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : <UserPlus size={15} />} Add member</button></div>
      </form>
    </Panel>
  );
}

function ImportTab() {
  const toast = useToast();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [opts, setOpts] = useState({ send_welcome_email: false, skip_errors: true });
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<{ level: string; text: string }[]>([]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('send_welcome_email', String(opts.send_welcome_email));
    fd.append('skip_errors', String(opts.skip_errors));
    try {
      const { data } = await api.post('/api/users/bulk-import', fd);
      setMessages(data.messages ?? []);
      void qc.invalidateQueries({ queryKey: ['org'] });
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  return (
    <Panel title="Import many members from a CSV or Excel file"
      actions={<div className="row-tight">
        <button className="btn btn-secondary btn-sm" onClick={() => downloadFile('/api/users/bulk-import/template', { format: 'csv' }, 'users_template.csv')}><Download size={13} /> CSV template</button>
        <button className="btn btn-secondary btn-sm" onClick={() => downloadFile('/api/users/bulk-import/template', { format: 'excel' }, 'users_template.xlsx')}><Download size={13} /> Excel template</button>
      </div>}>
      <p className="muted small" style={{ marginTop: 0 }}>Columns: username, email, first_name, last_name, user_type (Student, Researcher, Teacher or Reviewer) and optionally password, phone, address. Everyone imported joins this workspace.</p>
      <form onSubmit={submit} className="stack">
        <input className="input" type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <label className="check"><input type="checkbox" checked={opts.send_welcome_email} onChange={(e) => setOpts((o) => ({ ...o, send_welcome_email: e.target.checked }))} /> <span>Email each person their sign-in details</span></label>
        <label className="check"><input type="checkbox" checked={opts.skip_errors} onChange={(e) => setOpts((o) => ({ ...o, skip_errors: e.target.checked }))} /> <span>Skip rows with errors and import the rest</span></label>
        <div><button className="btn btn-primary" disabled={!file || busy}>{busy ? <Spinner /> : <Upload size={15} />} Import</button></div>
      </form>
      {messages.map((m, i) => <div key={i} className={`notice ${m.level === 'error' ? 'notice-danger' : m.level === 'warning' ? 'notice-warn' : 'notice-ok'}`} style={{ marginTop: 10 }}>{m.text}</div>)}
    </Panel>
  );
}

export interface Reviewer {
  user_id: number; name: string; username: string; email: string; user_type_display: string; is_active: boolean;
  source: 'member' | 'turacoz'; assigned_to_us: boolean;
  assigned: number; completed: number; pending: number; in_progress: number; overdue: number;
}
export interface ReviewItem {
  id: number; document_id: number; document_name: string; document_number: string; version: string;
  status: 'completed' | 'overdue' | 'in_progress' | 'pending'; status_label: string;
  assigned_at: string | null; review_date: string | null; completed_at: string | null;
}

/** Everyone who reviews our documents — our members and the Turacoz reviewers — with their numbers. */
function ReviewersTab() {
  const toast = useToast();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ['org', 'reviewers'], queryFn: async () => (await api.get('/api/org/reviewers')).data as { reviewers: Reviewer[]; totals: Reviewer } });
  const download = async (format: 'xlsx' | 'csv') => {
    try { await downloadFile('/api/org/review-report', { format }, `reviewers.${format}`); }
    catch (err) { toast.error(errorMessage(err)); }
  };
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <ErrorNotice error={q.error} />;
  const t = q.data.totals;
  const columns: Column<Reviewer>[] = [
    { key: 'name', header: 'Reviewer', value: (r) => `${r.name} ${r.username} ${r.email}`, render: (r) => (
      <div><div className="org-name">{r.name}</div><div className="tiny faint">{r.username} · {r.email}</div></div>) },
    { key: 'source', header: 'From', value: (r) => r.source, render: (r) => r.source === 'turacoz'
      ? <Badge tone="accent">Turacoz</Badge> : <Badge>Our member</Badge> },
    { key: 'assigned', header: 'Assigned', sortable: true },
    { key: 'completed', header: 'Done', sortable: true },
    { key: 'pending', header: 'Pending', sortable: true, render: (r) => <>{r.pending}{r.in_progress > 0 && <div className="tiny faint">{r.in_progress} started</div>}</> },
    { key: 'overdue', header: 'Overdue', sortable: true, render: (r) => r.overdue > 0 ? <Badge tone="danger">{r.overdue}</Badge> : <span className="faint">0</span> },
  ];
  return (
    <div className="stack-lg">
      <div className="stat-grid">
        <Stat value={t.assigned} label="Reviews of our documents" />
        <Stat value={t.completed} label="Completed" />
        <Stat value={t.pending} label="Pending" note={`${t.in_progress} started`} />
        <Stat value={t.overdue} label="Overdue" note={t.overdue ? 'Past the review date' : 'None'} />
      </div>
      <Panel title={`Reviewers (${q.data.reviewers.length})`} flush actions={<div className="row-tight">
        <button className="btn btn-secondary btn-sm" onClick={() => download('xlsx')}><Download size={13} /> Report (Excel)</button>
        <button className="btn btn-ghost btn-sm" onClick={() => download('csv')}><Download size={13} /> CSV</button>
      </div>}>
        <DataTable rows={q.data.reviewers} columns={columns} rowKey={(r) => r.user_id} empty="Nobody reviews your documents yet."
          onRowClick={(r) => navigate(`/content-lab-management/organisation/reviewers/${r.user_id}/`)} />
      </Panel>
    </div>
  );
}

interface Person { user_id: number; username: string; email: string; phone: string | null; name: string }
interface Contacts {
  pocs: (Person & { designation: string; role: string })[];
  turacoz: (Person & { id: number; role_label: string; designation: string; is_active: boolean })[];
}

/** The workspace's points of contact (chosen here) and the Turacoz team assigned to it (read-only). */
function PocsTab() {
  const toast = useToast();
  const qc = useQueryClient();
  const contacts = useQuery({ queryKey: ['org', 'contacts'], queryFn: async () => (await api.get('/api/org/contacts')).data as Contacts });
  const members = useMembers('active');
  const [memberId, setMemberId] = useState('');
  const [title, setTitle] = useState('');
  const setPoc = async (userId: number | string, isPoc: boolean, designation = '') => {
    try {
      const { data } = await api.post(`/api/org/members/${userId}/poc`, { is_poc: isPoc, designation });
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['org'] });
      setMemberId(''); setTitle('');
    } catch (err) { toast.error(errorMessage(err)); }
  };
  if (contacts.isLoading) return <Loading />;
  if (contacts.isError || !contacts.data) return <ErrorNotice error={contacts.error} />;
  const options = (members.data ?? []).filter((m) => !m.is_poc)
    .map((m) => ({ value: String(m.user_id), label: `${`${m.first_name} ${m.last_name}`.trim() || m.username} (${m.username})` }));
  return (
    <div className="grid-2 org-pocs">
      <Panel title="Our points of contact" flush>
        <div className="org-poc-add">
          <div className="grow"><SearchSelect options={options} value={memberId} onChange={(v) => setMemberId(String(v ?? ''))} placeholder="Choose a member…" /></div>
          <input className="input" placeholder="Designation, e.g. Dean" value={title} onChange={(e) => setTitle(e.target.value)} style={{ maxWidth: 200 }} />
          <button className="btn btn-primary" disabled={!memberId} onClick={() => setPoc(memberId, true, title)}><UserPlus size={14} /> Add</button>
        </div>
        {contacts.data.pocs.length === 0
          ? <div className="panel-body muted small">Choose who Turacoz should contact about your workspace.</div>
          : <PeopleTable rows={contacts.data.pocs.map((p) => ({ key: `p${p.user_id}`, person: p, badge: 'PoC', designation: p.designation,
              action: <button className="btn btn-ghost btn-sm" onClick={() => setPoc(p.user_id, false)}><X size={13} /> Remove</button> }))} />}
      </Panel>
      <Panel title="Your Turacoz team" flush>
        {contacts.data.turacoz.length === 0
          ? <div className="panel-body muted small">Turacoz has not assigned a PoC or reviewer to your workspace yet.</div>
          : <PeopleTable rows={contacts.data.turacoz.map((t) => ({ key: `t${t.id}`, person: t, badge: t.role_label, designation: t.designation }))} />}
        <div className="panel-body tiny faint">Assigned by Turacoz. Reviewers listed here can review your documents.</div>
      </Panel>
    </div>
  );
}

function PeopleTable({ rows }: { rows: { key: string; person: Person; badge: string; designation: string; action?: ReactNode }[] }) {
  return (
    <div className="table-scroll">
      <table className="tbl">
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td><div className="org-name">{r.person.name}</div><div className="tiny faint">{r.designation || '—'}</div></td>
              <td><Badge tone="accent">{r.badge}</Badge></td>
              <td className="small"><a href={`mailto:${r.person.email}`}>{r.person.email}</a>{r.person.phone && <div className="faint">{r.person.phone}</div>}</td>
              {r.action !== undefined && <td>{r.action}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SettingsTab({ overview }: { overview: Overview }) {
  const toast = useToast();
  const qc = useQueryClient();
  const { refresh } = useAuth();
  const org = overview.organisation;
  const [name, setName] = useState(org.name);
  const [website, setWebsite] = useState(org.website);
  const [logo, setLogo] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async (e: FormEvent, removeLogo = false) => {
    e.preventDefault();
    setBusy(true);
    const fd = new FormData();
    fd.append('name', name);
    fd.append('website', website);
    if (logo) fd.append('logo', logo);
    if (removeLogo) fd.append('remove_logo', 'true');
    try {
      const { data } = await api.post('/api/org/settings', fd);
      toast.success(data.message);
      setLogo(null);
      void qc.invalidateQueries({ queryKey: ['org'] });
      await refresh(); // logo and name in the sidebar
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  return (
    <Panel title="Workspace settings">
      <form onSubmit={save} className="form-grid">
        <Field label="Name" required><input className="input" required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Website"><input className="input" type="url" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://" /></Field>
        <div className="span-2 org-logo-row">
          <div className="org-logo-preview">{org.logo_url ? <img src={org.logo_url} alt={`${org.name} logo`} /> : <span className="faint small">No logo</span>}</div>
          <Field label="Logo" help="PNG or JPG, up to 2 MB.">
            <input className="input" type="file" accept="image/png,image/jpeg" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
          </Field>
          {org.logo_url && <button type="button" className="btn btn-ghost btn-sm" onClick={(e) => save(e, true)}>Remove logo</button>}
        </div>
        <div className="span-2"><button className="btn btn-primary" disabled={busy}>{busy && <Spinner />} Save changes</button></div>
      </form>
    </Panel>
  );
}


interface BillingProfile {
  legal_name: string; address: string; state: string; state_code: string; country: string; gstin: string;
  billing_email: string; billing_cycle: string; billing_cycle_label: string; missing: string[];
}

/** Who invoices are made out to. Turacoz sets whether the workspace is billed per submission or monthly. */
function BillingTab() {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['org', 'billing-profile'], queryFn: async () => (await api.get<BillingProfile>('/api/org/billing-profile')).data });
  const [form, setForm] = useState<BillingProfile | null>(null);
  const [busy, setBusy] = useState(false);
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const f = form ?? q.data;
  const set = (k: keyof BillingProfile) => (e: { target: { value: string } }) => setForm({ ...f, [k]: e.target.value });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.put('/api/org/billing-profile', f);
      toast.success(data.message);
      qc.setQueryData(['org', 'billing-profile'], data);
      setForm(null);
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  return (
    <Panel title="Billing details">
      {q.data.missing.length > 0 && (
        <p className="small" style={{ marginTop: 0, color: 'var(--danger)' }}>Add your {q.data.missing.join(' and ')} so that invoices can be generated — GST depends on it.</p>
      )}
      <form className="form-grid" onSubmit={save}>
        <div className="span-2"><Field label="Name on invoices" help="Legal name, if different from the workspace name.">
          <input className="input" value={f.legal_name} onChange={set('legal_name')} /></Field></div>
        <div className="span-2"><Field label="Billing address"><textarea className="input" rows={2} value={f.address} onChange={set('address')} /></Field></div>
        <Field label="Country" required><input className="input" required value={f.country} onChange={set('country')} /></Field>
        <Field label="State" required={f.country.trim().toLowerCase() === 'india'}><input className="input" value={f.state} onChange={set('state')} /></Field>
        <Field label="State code" help="GST state code, e.g. 07 for Delhi"><input className="input" value={f.state_code} onChange={set('state_code')} maxLength={5} /></Field>
        <Field label="GSTIN" help="Optional"><input className="input" value={f.gstin} onChange={set('gstin')} maxLength={20} /></Field>
        <Field label="Billing email" help="Also receives invoices, besides the administrators."><input className="input" type="email" value={f.billing_email} onChange={set('billing_email')} /></Field>
        <Field label="Billing cycle"><input className="input" value={q.data.billing_cycle_label} disabled /></Field>
        <div className="span-2"><button className="btn btn-primary" disabled={busy}>{busy && <Spinner />} Save billing details</button></div>
      </form>
    </Panel>
  );
}
