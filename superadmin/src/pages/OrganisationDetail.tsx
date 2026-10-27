/** One workspace in tabs: overview (counts, join code), members, join requests, settings (details, logo, status). */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ChangeListView } from './ChangeList';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Download, Eye, Key, KeyRound, Pencil, RefreshCw, Shield, ShieldCheck, UserCheck, UserPlus, UserX, X } from 'lucide-react';
import { api, downloadFile, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Badge, ErrorNotice, Field, Loading, PageHeader, Pagination, Panel, SearchInput, SearchSelect, Spinner, Stat, Tabs, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';
import { OrgRateCard } from '@/components/OrgRateCard';
import { OrgBilling } from '@/components/OrgBilling';
import { OrgLogo, STATUS_TONE, type OrgRow } from './Organisations';
import { LABEL as SUB_LABEL, TONE as SUB_TONE, type Resp as SubResp } from './Subscriptions';

interface Member {
  user_id: number; username: string; email: string; name: string; user_type_display: string;
  role: 'admin' | 'member'; status: string; is_active: boolean; documents: number; joined_at: string | null;
  is_poc: boolean; designation: string;
  /** review assignments of this member (as a reviewer) */
  reviews: { assigned: number; completed: number; pending: number; in_progress: number; overdue: number };
  /** for Turacoz team members: the workspaces they are assigned to */
  assigned_to: string[];
  reviews_by_organisation: { organisation: string; assigned: number; completed: number; pending: number; in_progress: number; overdue: number }[];
}

interface Person { user_id: number; username: string; email: string; phone: string | null; name: string }
interface Contacts {
  pocs: (Person & { designation: string; role: string })[];
  turacoz: (Person & { id: number; role: 'poc' | 'reviewer' | 'finance'; role_label: string; designation: string; is_active: boolean })[];
}

export default function OrganisationDetail() {
  const { orgId } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get('tab') as Tab | null) ?? 'overview';
  const dataList = DATA_LISTS.find((l) => l.value === tab);
  const moreList = dataList && !dataList.main ? dataList : undefined;
  const setTab = (t: Tab) => setSp(t === 'overview' ? {} : { tab: t }, { replace: true });
  const q = useQuery({
    queryKey: ['admin', 'organisations', 'detail', orgId],
    queryFn: async () => (await api.get<{ organisation: OrgRow; members: Member[]; contacts: Contacts }>(`/api/superadmin/organisations/${orgId}`)).data,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin', 'organisations'] });
  const post = async (path: string, body?: unknown) => {
    try {
      const { data } = await api.post(`/api/superadmin/organisations/${orgId}${path}`, body);
      toast.success(data.message);
      await refresh();
    } catch (err) { toast.error(errorMessage(err)); }
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const { organisation: org, members, contacts } = q.data!;
  const hasContacts = org.kind === 'university' || org.kind === 'organisation';
  // an individual workspace has no join code, so nobody can ask to join it
  const isIndividual = org.kind === 'individual';
  const view: Tab = isIndividual && tab === 'requests' ? 'overview' : tab;

  const toggleActive = async (m: Member) => {
    const deactivate = m.is_active;
    if (!(await confirm({ title: deactivate ? 'Deactivate user' : 'Activate user', danger: deactivate,
      message: `Are you sure you want to ${deactivate ? 'deactivate' : 'activate'} ${m.username}?`,
      confirmLabel: deactivate ? 'Deactivate' : 'Activate' }))) return;
    try {
      const { data } = await api.post(`/api/users/${m.user_id}/toggle-status`);
      toast.success(data.message);
      await refresh();
    } catch (err) { toast.error(errorMessage(err)); }
  };

  const setStatus = async (status: OrgRow['status']) => {
    if (status !== 'active' && !(await confirm({ title: `Set ${org.name} to ${status}`, danger: true, confirmLabel: 'Continue',
      message: `Members of ${org.name} will not be able to sign in while it is ${status}.` }))) return;
    await post('/status', { status });
  };

  const active = members.filter((m) => m.status === 'active');
  const pending = members.filter((m) => m.status === 'pending');
  const admins = active.filter((m) => m.role === 'admin');
  const documents = members.reduce((n, m) => n + m.documents, 0);
  const isTeam = org.kind === 'system';
  const reviewTotals = active.reduce((t, m) => ({
    assigned: t.assigned + m.reviews.assigned, completed: t.completed + m.reviews.completed,
    pending: t.pending + m.reviews.pending, overdue: t.overdue + m.reviews.overdue,
  }), { assigned: 0, completed: 0, pending: 0, overdue: 0 });

  return (
    <>
      <Crumbs items={[{ label: 'Organisations', to: '/organisations/' }, { label: org.name }]} />
      <PageHeader eyebrow={<span className="cap">{org.kind}</span>}
        title={<span className="row-tight"><OrgLogo org={org} size={40} /> {org.name}</span>}
        subtitle={<>Status <Badge tone={STATUS_TONE[org.status]}>{org.status}</Badge>{org.approved_at && <> · approved {formatDate(org.approved_at)}</>}</>}
        actions={<div className="row-tight">
          {org.status !== 'active' && <button className="btn btn-primary" onClick={() => setStatus('active')}>{org.status === 'pending' ? 'Approve' : 'Activate'}</button>}
          {org.status === 'pending' && <button className="btn btn-secondary" onClick={() => setStatus('rejected')}>Reject</button>}
          {org.status === 'active' && <button className="btn btn-secondary" onClick={() => setStatus('suspended')}>Suspend</button>}
        </div>} />

      <div className="org-tabs">
        <Tabs<Tab> value={view} onChange={setTab} tabs={[
          { value: 'overview', label: 'Overview' },
          { value: 'members', label: `Members (${active.length})` },
          ...(isIndividual ? [] : [{ value: 'requests' as Tab, label: <>Join requests{pending.length > 0 && <span className="org-count">{pending.length}</span>}</> }]),
          ...(hasContacts ? [{ value: 'pocs' as Tab, label: 'PoCs' }] : []),
          ...DATA_LISTS.filter((l) => l.main).map((l) => ({ value: l.value as Tab, label: l.label })),
          { value: 'settings', label: 'Settings' },
        ]} />
        <label className={`org-more ${moreList ? 'active' : ''}`}>
          <select className="input" value={moreList?.value ?? ''} onChange={(e) => e.target.value && setTab(e.target.value as Tab)} aria-label="More workspace data">
            <option value="" disabled>More…</option>
            {DATA_LISTS.filter((l) => !l.main).map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </label>
      </div>

      {dataList && <ChangeListView key={dataList.value} app={dataList.app} model={dataList.model} workspace={org.id} embedded />}

      {view === 'overview' && (
        <div className="stack-lg">
          <div className="stat-grid">
            <Stat value={active.length} label="Members" />
            {isTeam ? <>
              <Stat value={reviewTotals.assigned} label="Reviews assigned" note={`${reviewTotals.completed} completed`} />
              <Stat value={reviewTotals.pending} label="Reviews pending" note={reviewTotals.overdue ? `${reviewTotals.overdue} past the review date` : 'None overdue'} />
            </> : <>
              {!isIndividual && <Stat value={pending.length} label="Join requests" note={pending.length ? 'Waiting for approval' : undefined} />}
              <Stat value={documents} label="Documents" />
            </>}
            {isIndividual
              ? <Stat value={active[0]?.name || active[0]?.username || '—'} label="Owner" note="Manages the workspace and its plans" />
              : <Stat value={admins.length} label="Administrators" note={admins.map((a) => a.name || a.username).join(', ') || 'None yet'} />}
          </div>
          <div className="grid-2">
            <Panel title="Workspace">
              <dl className="kv">
                <dt>Type</dt><dd className="cap">{org.kind}</dd>
                <dt>Website</dt><dd>{org.website ? <a href={org.website} target="_blank" rel="noreferrer">{org.website}</a> : '—'}</dd>
                <dt>Registered</dt><dd>{org.created_at ? formatDate(org.created_at) : '—'}</dd>
                <dt>Approved</dt><dd>{org.approved_at ? formatDate(org.approved_at) : '—'}</dd>
              </dl>
            </Panel>
            {!isIndividual && <Panel title="Join code">
              {org.join_code ? <>
                <p className="muted small" style={{ marginTop: 0 }}>Students and researchers enter this code when they sign up; the workspace administrator approves them.</p>
                <div className="row-tight"><code className="org-code">{org.join_code}</code>
                  <button className="btn btn-ghost btn-sm" onClick={() => post('/join-code/regenerate')}><RefreshCw size={13} /> New code</button></div>
              </> : <p className="muted small">No join code yet — it is created when the workspace is saved.</p>}
            </Panel>}
          </div>
          {!isTeam && <OrgPlans orgId={org.id} orgName={org.name} waiting={org.status === 'pending'} />}
          {hasContacts && <OrgRateCard orgId={org.id} orgName={org.name} />}
          {hasContacts && <OrgBilling orgId={org.id} orgName={org.name} />}
        </div>
      )}

      {tab === 'members' && (
        <Panel title={`Members (${active.length})`} flush
          actions={isTeam && <ReportButtons orgId={org.id} />}>
          {org.kind !== 'individual' && <AddMember orgId={org.id} onDone={refresh} />}
          <MembersTable org={org} rows={active} post={post} toggleActive={toggleActive} />
        </Panel>
      )}

      {view === 'requests' && (
        pending.length === 0
          ? <Panel><p className="muted" style={{ margin: 0 }}>No pending join requests. People who sign up with the join code appear here until the workspace administrator (or you) approves them.</p></Panel>
          : (
            <Panel title={`Join requests (${pending.length})`} flush>
              <div className="table-wrap">
                <table className="tbl">
                  <thead><tr><th>Person</th><th>Type</th><th>Requested</th><th>Actions</th></tr></thead>
                  <tbody>
                    {pending.map((m) => (
                      <tr key={m.user_id}>
                        <td><strong>{m.name || m.username}</strong><span className="tiny faint" style={{ display: 'block' }}>{m.username} · {m.email}</span></td>
                        <td>{m.user_type_display}</td>
                        <td className="nowrap">{m.joined_at ? formatDate(m.joined_at) : ''}</td>
                        <td><div className="row-tight">
                          <button className="btn btn-primary btn-sm" onClick={() => post('/members', { user_id: m.user_id, role: 'member', status: 'active' })}><Check size={13} /> Approve</button>
                          <button className="btn btn-secondary btn-sm" onClick={() => post('/members', { user_id: m.user_id, role: 'member', status: 'rejected' })}><X size={13} /> Reject</button>
                        </div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )
      )}

      {tab === 'pocs' && hasContacts && (
        <PocsTab orgId={org.id} orgName={org.name} contacts={contacts} members={active} post={post} onChange={refresh} />
      )}

      {tab === 'settings' && (
        <div className="grid-2">
          <DetailsForm org={org} onSaved={refresh} />
          <Panel title="Status">
            <p className="muted small" style={{ marginTop: 0 }}>
              Members can sign in only while the workspace is <strong>active</strong>. Suspending it signs everyone out at their next request.
            </p>
            <div className="row-tight">
              <Badge tone={STATUS_TONE[org.status]}>{org.status}</Badge>
              {org.status !== 'active' && <button className="btn btn-primary btn-sm" onClick={() => setStatus('active')}>{org.status === 'pending' ? 'Approve' : 'Activate'}</button>}
              {org.status === 'active' && <button className="btn btn-secondary btn-sm" onClick={() => setStatus('suspended')}>Suspend</button>}
              {org.status === 'pending' && <button className="btn btn-secondary btn-sm" onClick={() => setStatus('rejected')}>Reject</button>}
            </div>
          </Panel>
        </div>
      )}
    </>
  );
}

/** The workspace's plans (bought, given or on trial); managed on the Subscriptions page. */
function OrgPlans({ orgId, orgName, waiting }: { orgId: number; orgName: string; waiting: boolean }) {
  const q = useQuery({
    queryKey: ['admin', 'subscriptions', 'org', orgId],
    queryFn: async () => (await api.get<SubResp>('/api/superadmin/subscriptions', { params: { organisation_id: orgId } })).data,
  });
  const rows = (q.data?.items ?? []).filter((s) => s.state !== 'cancelled');
  return (
    <Panel title="Plans" flush actions={<Link className="btn btn-ghost btn-sm" to={`/subscriptions/?q=${encodeURIComponent(orgName)}`}>Manage</Link>}>
      {q.isLoading ? <div className="panel-body"><Loading /></div> : rows.length === 0 ? (
        <div className="panel-body"><p className="muted small" style={{ margin: 0 }}>No plan yet — only free tools and tools given per user.</p></div>
      ) : (
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr><th>Plan</th><th>Tools</th><th>Period</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td><strong>{s.plan_name}</strong></td>
                  <td className="small">{s.tools.map((t) => t.name).join(', ')}</td>
                  <td className="small nowrap">{s.starts_at ? formatDate(s.starts_at) : '—'} → {s.ends_at ? formatDate(s.ends_at) : 'no end'}</td>
                  <td>{waiting && s.state === 'pending' ? <Badge tone="accent">Chosen at sign-up</Badge>
                    : <Badge tone={SUB_TONE[s.state]}>{s.is_trial && s.state === 'active' ? 'Free trial' : SUB_LABEL[s.state]}</Badge>}
                    {waiting && s.state === 'pending' && <span className="tiny faint" style={{ display: 'block' }}>Starts when you approve</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

type Tab = 'overview' | 'members' | 'requests' | 'pocs' | 'settings' | (typeof DATA_LISTS)[number]['value'];

/** The workspace's own data, each list limited to this organisation. `main` lists get their own tab,
 * the rest are picked from the "More…" list so the tabs fit on one line. */
const DATA_LISTS = [
  { value: 'documents', label: 'Documents', app: 'documents', model: 'document', main: true },
  { value: 'references', label: 'References', app: 'library', model: 'referencedocument', main: true },
  { value: 'zips', label: 'Reference ZIPs', app: 'library', model: 'referencezip', main: false },
  { value: 'reviews', label: 'Review assignments', app: 'library', model: 'assignedreviewer', main: false },
  { value: 'versions', label: 'Document versions', app: 'documents', model: 'documentversion', main: false },
  { value: 'permissions', label: 'User permissions', app: 'authentication', model: 'userpermission', main: false },
  { value: 'roles', label: 'User roles', app: 'authentication', model: 'userrole', main: false },
  { value: 'mail', label: 'Mail logs', app: 'documents', model: 'emaillog', main: false },
  { value: 'notifications', label: 'Notifications', app: 'documents', model: 'notification', main: false },
  { value: 'annotations', label: 'Document annotations', app: 'documents', model: 'documentannotation', main: false },
  { value: 'annotation-activity', label: 'Annotation activities', app: 'documents', model: 'annotationactivity', main: false },
  { value: 'sharing', label: 'Document sharing', app: 'documents', model: 'documentsharing', main: false },
  { value: 'version-sharing', label: 'Document version sharing', app: 'documents', model: 'documentversionsharing', main: false },
  { value: 'document-references', label: 'Document references', app: 'documents', model: 'documentreference', main: false },
  { value: 'version-references', label: 'Document version references', app: 'documents', model: 'documentversionreference', main: false },
  { value: 'history', label: 'Document history', app: 'library', model: 'documenthistory', main: false },
  { value: 'temporary-passwords', label: 'Temporary passwords', app: 'library', model: 'temporarypassword', main: false },
  { value: 'journal-selections', label: 'Journal selections', app: 'documents', model: 'userjournalselection', main: false },
  { value: 'enrolled', label: 'Enrolled users', app: 'documents', model: 'enrolluser', main: false },
  { value: 'feedback', label: 'Feedback', app: 'documents', model: 'feedback', main: false },
  { value: 'support', label: 'Support requests', app: 'documents', model: 'support', main: false },
] as const;

/** Points of contact: the university's own (members) and the Turacoz team assigned to it. */
function PocsTab({ orgId, orgName, contacts, members, post, onChange }: {
  orgId: number; orgName: string; contacts: Contacts; members: Member[];
  post: (path: string, body?: unknown) => Promise<void>; onChange: () => void;
}) {
  const toast = useToast();
  const [memberId, setMemberId] = useState('');
  const [memberTitle, setMemberTitle] = useState('');
  const [staffId, setStaffId] = useState('');
  const [staffRole, setStaffRole] = useState<'' | 'poc' | 'reviewer' | 'finance'>('');  // chosen deliberately
  const [staffTitle, setStaffTitle] = useState('');
  const [staffOptions, setStaffOptions] = useState<{ value: string; label: string }[]>([]);
  const memberOptions = members.filter((m) => !m.is_poc)
    .map((m) => ({ value: String(m.user_id), label: `${m.name || m.username} (${m.username})` }));
  const findStaff = async (q: string) => {
    const { data } = await api.get('/api/superadmin/organisations/system-users/search', { params: { q } });
    setStaffOptions(data.users.map((u: { id: number; name: string; username: string; user_type_display: string }) => (
      { value: String(u.id), label: `${u.name || u.username} (${u.username}) · ${u.user_type_display}` })));
  };
  useEffect(() => { void findStaff(''); }, []);
  const addPoc = async () => {
    if (!memberId) return;
    await post(`/members/${memberId}/poc`, { is_poc: true, designation: memberTitle });
    setMemberId(''); setMemberTitle('');
  };
  const addStaff = async () => {
    if (!staffId || !staffRole) return;
    await post('/assignments', { user_id: Number(staffId), role: staffRole, designation: staffTitle });
    setStaffId(''); setStaffTitle(''); setStaffRole('');
  };
  const removeStaff = async (id: number) => {
    try {
      const { data } = await api.delete(`/api/superadmin/organisations/${orgId}/assignments/${id}`);
      toast.success(data.message);
      onChange();
    } catch (err) { toast.error(errorMessage(err)); }
  };
  return (
    <div className="grid-2 pocs-grid">
      <Panel title={`${orgName} points of contact`} flush>
        <div className="org-add">
          <div className="grow"><SearchSelect options={memberOptions} value={memberId} onChange={(v) => setMemberId(String(v ?? ''))} placeholder="Choose a member…" /></div>
          <input className="input" style={{ width: 170 }} placeholder="Designation" value={memberTitle} onChange={(e) => setMemberTitle(e.target.value)} />
          <button className="btn btn-primary" disabled={!memberId} onClick={addPoc}><UserPlus size={14} /> Add</button>
        </div>
        <ContactList empty="No points of contact yet. The university admin can also choose them on their University page."
          rows={contacts.pocs.map((p) => ({ key: `m${p.user_id}`, person: p, badge: p.role === 'admin' ? 'Admin' : 'Member', designation: p.designation,
            remove: () => post(`/members/${p.user_id}/poc`, { is_poc: false }) }))} />
      </Panel>
      <Panel title="Turacoz team" flush>
        <div className="org-add">
          <div className="grow"><SearchSelect options={staffOptions} value={staffId} onChange={(v) => setStaffId(String(v ?? ''))} onSearch={findStaff} placeholder="Find a Turacoz system user…" /></div>
          <select className="input" style={{ width: 170 }} value={staffRole} onChange={(e) => setStaffRole(e.target.value as 'poc' | 'reviewer' | 'finance')} aria-label="Role">
            <option value="" disabled>Role…</option><option value="poc">PoC</option><option value="reviewer">Reviewer</option>
            <option value="finance">Financial Manager</option>
          </select>
          <input className="input" style={{ width: 150 }} placeholder="Designation" value={staffTitle} onChange={(e) => setStaffTitle(e.target.value)} />
          <button className="btn btn-primary" disabled={!staffId || !staffRole} onClick={addStaff}><UserPlus size={14} /> Assign</button>
        </div>
        <ContactList empty="No Turacoz team member is assigned yet. Assigned reviewers can review this workspace's documents; its Financial Manager approves its invoices (otherwise the default Financial Managers do)."
          rows={contacts.turacoz.map((t) => ({ key: `t${t.id}`, person: t, badge: t.role_label, designation: t.designation,
            inactive: !t.is_active, remove: () => removeStaff(t.id) }))} />
      </Panel>
    </div>
  );
}

function ContactList({ rows, empty }: {
  rows: { key: string; person: Person; badge: string; designation: string; inactive?: boolean; remove: () => void }[]; empty: string;
}) {
  if (!rows.length) return <div className="panel-body muted small">{empty}</div>;
  return (
    <div className="table-wrap">
      <table className="tbl">
        <thead><tr><th>Name</th><th>Role</th><th>Contact</th><th /></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td><strong>{r.person.name}</strong><span className="tiny faint" style={{ display: 'block' }}>{r.designation || '—'}</span></td>
              <td><span className="row-tight wrap"><Badge tone="accent">{r.badge}</Badge>{r.inactive && <Badge tone="danger">Inactive</Badge>}</span></td>
              <td className="small"><a href={`mailto:${r.person.email}`}>{r.person.email}</a>{r.person.phone && <span className="faint" style={{ display: 'block' }}>{r.person.phone}</span>}</td>
              <td><button className="btn btn-ghost btn-sm" onClick={r.remove}><X size={13} /> Remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Each workspace the member works for, with its own review numbers. */
function AssignedTo({ m }: { m: Member }) {
  const counts = new Map(m.reviews_by_organisation.map((r) => [r.organisation, r]));
  const names = [...new Set([...m.assigned_to.map((a) => a.replace(/ \((PoC|Reviewer)\)$/, '')), ...counts.keys()])];
  if (!names.length) return <span className="faint">Not assigned</span>;
  return (
    <ul className="assigned-list">
      {names.map((name) => {
        const roles = m.assigned_to.filter((a) => a.startsWith(`${name} (`)).map((a) => a.slice(name.length + 2, -1));
        const r = counts.get(name);
        return (
          <li key={name}>
            <strong>{name}</strong>{roles.length > 0 && <span className="faint"> · {roles.join(', ')}</span>}
            {!roles.length && <span className="faint"> · no longer assigned</span>}
            <span className="tiny faint" style={{ display: 'block' }}>
              {r ? <>{r.assigned} reviews · {r.completed} done · {r.pending} pending{r.overdue > 0 && <span className="danger-text"> · {r.overdue} overdue</span>}</> : 'No reviews yet'}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Review work of every member, as one file. */
function ReportButtons({ orgId }: { orgId: number }) {
  const toast = useToast();
  const get = async (format: 'xlsx' | 'csv') => {
    try { await downloadFile(`/api/superadmin/organisations/${orgId}/review-report`, { format }, `review-report.${format}`); }
    catch (err) { toast.error(errorMessage(err)); }
  };
  return (
    <div className="row-tight">
      <button className="btn btn-secondary btn-sm" onClick={() => get('xlsx')}><Download size={13} /> Report (Excel)</button>
      <button className="btn btn-ghost btn-sm" onClick={() => get('csv')}><Download size={13} /> CSV</button>
    </div>
  );
}

const PAGE_SIZE = 25;

function MembersTable({ org, rows: all, post, toggleActive }: {
  org: OrgRow; rows: Member[]; post: (path: string, body?: unknown) => Promise<void>; toggleActive: (m: Member) => void;
}) {
  const isTeam = org.kind === 'system';
  const [f, setF] = useState({ q: '', role: '', type: '', status: '' });
  const [page, setPage] = useState(1);
  const set = (k: keyof typeof f) => (v: string) => { setF((cur) => ({ ...cur, [k]: v })); setPage(1); };
  const types = [...new Set(all.map((m) => m.user_type_display))].sort();
  const q = f.q.trim().toLowerCase();
  const filtered = all.filter((m) =>
    (!q || `${m.name} ${m.username} ${m.email}`.toLowerCase().includes(q))
    && (!f.role || m.role === f.role)
    && (!f.type || m.user_type_display === f.type)
    && (!f.status || (f.status === 'active') === m.is_active));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const rows = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const anyFilter = !!(f.q || f.role || f.type || f.status);
  return (
    <>
    <div className="org-filters">
      <SearchInput value={f.q} onChange={set('q')} placeholder="Name, username or email…" />
      <select className="input" value={f.role} onChange={(e) => set('role')(e.target.value)} aria-label="Role">
        <option value="">All roles</option><option value="admin">Administrators</option><option value="member">Members</option>
      </select>
      <select className="input" value={f.type} onChange={(e) => set('type')(e.target.value)} aria-label="Account type">
        <option value="">All account types</option>
        {types.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <select className="input" value={f.status} onChange={(e) => set('status')(e.target.value)} aria-label="Status">
        <option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option>
      </select>
      {anyFilter && <button className="btn btn-ghost btn-sm" onClick={() => { setF({ q: '', role: '', type: '', status: '' }); setPage(1); }}><X size={13} /> Clear</button>}
      <span className="small muted org-filter-count">{filtered.length} of {all.length}</span>
    </div>
    <div className="table-wrap">
      <table className="tbl">
        <thead><tr>
          <th>User</th>{!isTeam && <th>Type</th>}<th>Role</th><th>Status</th>
          {isTeam
            ? <><th>Assigned to</th><th className="num">Reviews</th><th className="num">Completed</th><th className="num">Pending</th><th className="num">Overdue</th></>
            : <><th>Documents</th><th>Joined</th></>}
          <th>Actions</th>
        </tr></thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.user_id}>
              <td>
                {isTeam
                  ? <Link className="act" to={`/organisations/${org.id}/members/${m.user_id}/`}><strong>{m.name || m.username}</strong></Link>
                  : <strong>{m.name || m.username}</strong>}
                <span className="tiny faint" style={{ display: 'block' }}>{m.username} · {m.email}</span></td>
              {!isTeam && <td>{m.user_type_display}</td>}
              <td><span className="row-tight wrap">{org.kind === 'individual' ? <Badge tone="accent">Owner</Badge> : m.role === 'admin' ? <Badge tone="accent">Admin</Badge> : 'Member'}
                {m.is_poc && <Badge tone="ok">PoC</Badge>}</span></td>
              <td>{m.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Inactive</Badge>}</td>
              {isTeam ? <>
                <td className="small"><AssignedTo m={m} /></td>
                <td className="num">{m.reviews.assigned}</td>
                <td className="num">{m.reviews.completed}</td>
                <td className="num">{m.reviews.pending}{m.reviews.in_progress > 0 && <span className="tiny faint" style={{ display: 'block' }}>{m.reviews.in_progress} started</span>}</td>
                <td className="num">{m.reviews.overdue > 0 ? <Badge tone="danger">{m.reviews.overdue}</Badge> : <span className="faint">0</span>}</td>
              </> : <>
                <td>{m.documents}</td>
                <td className="nowrap">{m.joined_at ? formatDate(m.joined_at) : ''}</td>
              </>}
              <td className="org-row-actions">
                <div className="row-tight nowrap">
                  <Link className="btn btn-ghost btn-icon" title="View Profile" to={`/library/user/${m.user_id}/view/`}><Eye size={14} /></Link>
                  <Link className="btn btn-ghost btn-icon" title="Edit User" to={`/library/user/${m.user_id}/edit/`}><Pencil size={14} /></Link>
                  <Link className="btn btn-ghost btn-icon" title="Manage Permissions" to={`/library/user/${m.user_id}/permissions/`}><Shield size={14} /></Link>
                  <Link className="btn btn-ghost btn-icon" title="Change Password" to={`/library/user/${m.user_id}/change-password/`}><Key size={14} /></Link>
                  <Link className="btn btn-ghost btn-icon" title="View Password" to={`/library/user/${m.user_id}/view-password/`}><KeyRound size={14} /></Link>
                  {org.kind !== 'individual' && (
                    <button className="btn btn-ghost btn-icon" title={m.role === 'admin' ? 'Remove as workspace admin' : 'Make workspace admin'}
                      onClick={() => post('/members', { user_id: m.user_id, role: m.role === 'admin' ? 'member' : 'admin', status: 'active' })}>
                      <ShieldCheck size={14} style={m.role === 'admin' ? { color: 'var(--accent)' } : undefined} />
                    </button>
                  )}
                  <button className="btn btn-ghost btn-icon" title={m.is_active ? 'Deactivate' : 'Activate'} onClick={() => toggleActive(m)}>
                    {m.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={isTeam ? 9 : 7} className="muted">No members found.</td></tr>}
        </tbody>
      </table>
    </div>
    {pages > 1 && <div className="org-pager"><Pagination page={current} pages={pages} total={filtered.length} onChange={setPage} /></div>}
    </>
  );
}

function DetailsForm({ org, onSaved }: { org: OrgRow; onSaved: () => void }) {
  const toast = useToast();
  const [name, setName] = useState(org.name);
  const [kind, setKind] = useState<string>(org.kind);
  const [website, setWebsite] = useState(org.website);
  const [logo, setLogo] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async (e: FormEvent, removeLogo = false) => {
    e.preventDefault();
    setBusy(true);
    const fd = new FormData();
    fd.append('name', name);
    fd.append('kind', kind);
    fd.append('website', website);
    if (logo) fd.append('logo', logo);
    if (removeLogo) fd.append('remove_logo', 'true');
    try {
      const { data } = await api.post(`/api/superadmin/organisations/${org.id}/update`, fd);
      toast.success(data.message);
      setLogo(null);
      onSaved();
    } catch (err) { toast.error(errorMessage(err)); }
    setBusy(false);
  };
  return (
    <Panel title="Details">
      <form onSubmit={save} className="stack">
        <Field label="Name" required><input className="input" required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Type">
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="university">University</option><option value="organisation">Organisation</option><option value="individual">Individual</option>
          </select>
        </Field>
        <Field label="Website"><input className="input" type="url" value={website} onChange={(e) => setWebsite(e.target.value)} /></Field>
        <Field label="Logo" help="PNG or JPG, up to 2 MB."><input className="input" type="file" accept="image/png,image/jpeg" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} /></Field>
        <div className="row-tight">
          <button className="btn btn-primary" disabled={busy}>{busy && <Spinner />} Save</button>
          {org.logo_url && <button type="button" className="btn btn-ghost" onClick={(e) => save(e, true)}>Remove logo</button>}
        </div>
      </form>
    </Panel>
  );
}

function AddMember({ orgId, onDone }: { orgId: number; onDone: () => void }) {
  const toast = useToast();
  const [userId, setUserId] = useState<string>('');
  const [role, setRole] = useState('member');
  const [options, setOptions] = useState<{ value: string; label: string }[]>([]);
  const search = async (text: string) => {
    const { data } = await api.get('/api/superadmin/organisations/users/search', { params: { q: text } });
    setOptions(data.users.map((u: { id: number; username: string; name: string; email: string; organisation: string | null }) => ({
      value: String(u.id), label: `${u.name || u.username} (${u.username}) — ${u.organisation ?? 'no workspace'}`,
    })));
  };
  const add = async () => {
    if (!userId) return;
    try {
      const { data } = await api.post(`/api/superadmin/organisations/${orgId}/members`, { user_id: Number(userId), role, status: 'active' });
      toast.success(data.message);
      setUserId('');
      onDone();
    } catch (err) { toast.error(errorMessage(err)); }
  };
  return (
    <div className="org-add">
      <div className="grow">
        <SearchSelect options={options} value={userId} onChange={(v) => setUserId(String(v ?? ''))} onSearch={search}
          placeholder="Find a user to add (moves them from their current workspace)…" />
      </div>
      <select className="input" value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role" style={{ width: 140 }}>
        <option value="member">Member</option><option value="admin">Administrator</option>
      </select>
      <button className="btn btn-primary" onClick={add} disabled={!userId}><UserPlus size={14} /> Add</button>
    </div>
  );
}
