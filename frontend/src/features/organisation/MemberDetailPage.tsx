/** One member of the admin's university / organisation: profile, documents, references, reviews, sign-ins. */
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, KeyRound, Mail, Phone, Shield, UserCheck, UserX } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDate, formatDateTime, timeAgo } from '@/lib/format';
import {
  Badge, DataTable, Empty, ErrorNotice, Loading, PageHeader, Panel, Stat, StageStatus, useConfirm, useToast, type Column,
} from '@/components/ui';
import './organisation.css';

interface Detail {
  member: {
    user_id: number; username: string; email: string; first_name: string; last_name: string; user_type_display: string;
    role: 'admin' | 'member'; status: string; is_active: boolean; date_joined: string | null; last_login: string | null;
    phone: string | null; address: string | null; is_self: boolean; roles: string[];
  };
  stats: { documents: number; by_stage: Record<string, number>; references: number; reviews_pending: number; reviews_completed: number };
  documents: { id: number; number: string; name: string; stage: string; stage_status: number; versions: number; created_at: string | null; updated_at: string | null }[];
  references: { id: number; number: string; name: string; type: string; created_at: string | null }[];
  reviews: { id: number; document_id: number | null; document: string; review_date: string | null; completed: boolean; completed_at: string | null; assigned_at: string | null }[];
  logins: { time: string | null; status: string; ip: string | null }[];
}

const STAGE_TONE: Record<number, 'muted' | 'warn' | 'ok' | 'danger'> = { 0: 'muted', 1: 'warn', 2: 'ok', 3: 'danger' };

export default function MemberDetailPage() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['org', 'member', userId],
    queryFn: async () => (await api.get(`/api/org/members/${userId}`)).data as Detail,
  });
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <ErrorNotice error={q.error} />;
  const { member: m, stats, documents, references, reviews, logins } = q.data;
  const name = `${m.first_name} ${m.last_name}`.trim() || m.username;

  const act = async (path: string, body?: unknown) => {
    try {
      const { data } = await api.post(path, body);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['org'] });
      return data;
    } catch (err) { toast.error(errorMessage(err)); }
  };
  const resetPassword = async () => {
    if (!(await confirm({ title: 'Reset password', message: `Create a new password for ${m.username}? Their current password stops working.`, confirmLabel: 'Reset' }))) return;
    const data = await act(`/api/org/members/${m.user_id}/reset-password`);
    if (data?.password) window.prompt(`New password for ${m.username} — share it with them securely:`, data.password);
  };
  const toggleActive = async () => {
    if (m.is_active && !(await confirm({ title: 'Deactivate account', danger: true, confirmLabel: 'Deactivate',
      message: `${name} will not be able to sign in until the account is activated again.` }))) return;
    await act(`/api/org/members/${m.user_id}/toggle-active`);
  };

  const docColumns: Column<Detail['documents'][number]>[] = [
    { key: 'name', header: 'Document', value: (d) => `${d.name} ${d.number}`, render: (d) => (
      <div><div className="org-name">{d.name}</div><div className="tiny faint mono">{d.number}</div></div>) },
    { key: 'stage', header: 'Status', render: (d) => <StageStatus label={d.stage} tone={STAGE_TONE[d.stage_status]} /> },
    { key: 'versions', header: 'Versions', sortable: true },
    { key: 'updated_at', header: 'Updated', sortable: true, render: (d) => (d.updated_at ? formatDate(d.updated_at) : '') },
  ];

  return (
    <>
      <PageHeader eyebrow={<Link to="/content-lab-management/organisation/" className="row-tight"><ArrowLeft size={13} /> Members</Link>}
        title={name}
        subtitle={<span className="row-tight wrap">
          <Badge>{m.user_type_display}</Badge>
          {m.role === 'admin' ? <Badge tone="accent">Administrator</Badge> : <Badge>Member</Badge>}
          {m.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Inactive</Badge>}
          <span className="small muted">{m.username}</span>
        </span>}
        actions={m.is_self ? undefined : (
          <div className="row-tight wrap">
            <button className="btn btn-secondary" onClick={() => act(`/api/org/members/${m.user_id}/role`, { role: m.role === 'admin' ? 'member' : 'admin' })}>
              <Shield size={14} /> {m.role === 'admin' ? 'Remove admin' : 'Make admin'}</button>
            <button className="btn btn-secondary" onClick={resetPassword}><KeyRound size={14} /> Reset password</button>
            <button className={`btn ${m.is_active ? 'btn-danger' : 'btn-primary'}`} onClick={toggleActive}>
              {m.is_active ? <><UserX size={14} /> Deactivate</> : <><UserCheck size={14} /> Activate</>}</button>
          </div>
        )} />

      <div className="stat-grid org-stats">
        <Stat value={stats.documents} label="Documents" note={`${stats.by_stage['Under Review'] ?? 0} under review · ${stats.by_stage.Approved ?? 0} approved`} />
        <Stat value={stats.by_stage.Draft ?? 0} label="Drafts" note={`${stats.by_stage['Draft Under Revision'] ?? 0} need revision`} />
        <Stat value={stats.references} label="References" />
        <Stat value={stats.reviews_pending} label="Reviews to do" note={`${stats.reviews_completed} completed`} />
      </div>

      <div className="org-detail-grid">
        <div className="stack-lg">
          <Panel title={`Documents (${documents.length})`} flush>
            {documents.length
              ? <DataTable rows={documents} columns={docColumns} rowKey={(d) => d.id} pageSize={10}
                  onRowClick={(d) => navigate(`/content-lab-management/document/${d.id}/`)} />
              : <div className="panel-body muted">No documents yet.</div>}
          </Panel>
          <Panel title={`References (${references.length})`} flush>
            {references.length ? (
              <DataTable rows={references} rowKey={(r) => r.id} pageSize={10} searchable={false}
                onRowClick={(r) => navigate(`/content-lab-management/reference-library/${r.id}/`)}
                columns={[
                  { key: 'name', header: 'Reference', render: (r) => <div><div className="org-name">{r.name}</div><div className="tiny faint mono">{r.number}</div></div> },
                  { key: 'type', header: 'Type', render: (r) => <span className="cap">{r.type}</span> },
                  { key: 'created_at', header: 'Added', render: (r) => (r.created_at ? formatDate(r.created_at) : '') },
                ]} />
            ) : <div className="panel-body muted">No references yet.</div>}
          </Panel>
          {reviews.length > 0 && (
            <Panel title={`Review assignments (${reviews.length})`} flush>
              <DataTable rows={reviews} rowKey={(r) => r.id} pageSize={10} searchable={false}
                onRowClick={(r) => r.document_id && navigate(`/content-lab-management/document/${r.document_id}/`)}
                columns={[
                  { key: 'document', header: 'Document version', render: (r) => <span className="mono small">{r.document}</span> },
                  { key: 'review_date', header: 'Due', render: (r) => (r.review_date ? formatDate(r.review_date) : '') },
                  { key: 'completed', header: 'Status', render: (r) => r.completed ? <Badge tone="ok">Completed</Badge> : <Badge tone="warn">Pending</Badge> },
                ]} />
            </Panel>
          )}
        </div>
        <div className="stack-lg">
          <Panel title="Profile">
            <dl className="kv org-kv">
              <dt>Email</dt><dd><a href={`mailto:${m.email}`} className="row-tight"><Mail size={13} /> {m.email}</a></dd>
              <dt>Phone</dt><dd>{m.phone ? <span className="row-tight"><Phone size={13} /> {m.phone}</span> : '—'}</dd>
              <dt>Address</dt><dd>{m.address || '—'}</dd>
              <dt>Roles</dt><dd>{m.roles.length ? m.roles.join(', ') : '—'}</dd>
              <dt>Joined</dt><dd>{m.date_joined ? formatDate(m.date_joined) : '—'}</dd>
              <dt>Last sign-in</dt><dd>{m.last_login ? timeAgo(m.last_login) : 'Never'}</dd>
            </dl>
          </Panel>
          <Panel title="Recent sign-in activity" flush>
            {logins.length ? (
              <table className="tbl">
                <tbody>
                  {logins.map((l, i) => (
                    <tr key={i}>
                      <td className="nowrap small">{l.time ? formatDateTime(l.time) : ''}</td>
                      <td>{l.status === 'success' ? <Badge tone="ok">Signed in</Badge>
                        : l.status === 'logout' ? <Badge>Signed out</Badge>
                          : <Badge tone="danger">{l.status === 'blocked' ? 'Blocked' : 'Failed'}</Badge>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div className="panel-body"><Empty title="No sign-ins yet" /></div>}
          </Panel>
        </div>
      </div>
    </>
  );
}
