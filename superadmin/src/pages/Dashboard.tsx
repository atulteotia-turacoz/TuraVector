import { Link } from 'react-router-dom';
import { InvoiceApprovals } from '@/components/InvoiceApprovals';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, CircleAlert, Minus, Pencil, Plus } from 'lucide-react';
import { api } from '@/lib/api';
import { adminPath, useIndex, type AppEntry, type LogEntry } from '@/lib/admin';
import { formatDate, formatDateTime, timeAgo } from '@/lib/format';
import { ErrorNotice, Loading, PageHeader, Panel, Stat } from '@/components/ui';

/** Model list for one app — used by the per-app index page (/:app/). */
export function AppPanel({ app }: { app: AppEntry }) {
  return (
    <Panel title={<Link to={`/${app.app_label}/`} className="act">{app.name}</Link>} flush>
      <div className="table-scroll">
        <table className="tbl app-table">
          <caption className="visually-hidden">Models in the {app.name} application</caption>
          <tbody>
            {app.models.map((m) => (
              <tr key={m.label}>
                <th scope="row" style={{ textTransform: 'none', letterSpacing: 0, fontSize: 13.5, fontWeight: 500, color: 'var(--ink)', padding: '9px 14px', borderBottom: '1px solid var(--hairline)' }}>
                  <Link to={`/${m.app}/${m.model}/`}>{m.name}</Link>
                </th>
                <td className="num">{m.count ?? ''}</td>
                <td className="acts">
                  <span className="actions">
                    {m.perms.add && <Link className="act act-accent row-tight" to={`/${m.app}/${m.model}/add/`}><Plus size={12} /> Add</Link>}
                    <Link className="act row-tight" to={`/${m.app}/${m.model}/`}>{m.perms.change ? <><Pencil size={12} /> Change</> : 'View'}</Link>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function ActionFlag({ e }: { e: LogEntry }) {
  if (e.is_addition) return <span className="flag flag-add" title="Added"><Plus size={11} /></span>;
  if (e.is_deletion) return <span className="flag flag-delete" title="Deleted"><Minus size={11} /></span>;
  return <span className="flag flag-change" title="Changed"><Pencil size={10} /></span>;
}

interface Overview {
  users: { total: number; active: number; superusers: number; staff: number; new_30d: number };
  documents: { total: number; versions: number; new_30d: number; by_stage: { stage: number; label: string; count: number }[] };
  library: { references: number; zips: number; projects: number };
  emails: { by_status: Record<string, number>; total: number; last_30d: number };
  logins: {
    series: { date: string; success: number; failed: number }[];
    success_14d: number; failed_14d: number;
    recent: { id: number; username: string; name: string | null; status: string; ip: string; time: string }[];
  };
  health: {
    database: string; media_root: string; media_exists: boolean; smtp: string | null; email_fallback: string;
    pdftron_version: string; pdftron_licensed: boolean; onlyoffice_url: string; debug: boolean;
  };
}

const STAGE_TONE: Record<number, string> = { 0: 'var(--ink-3)', 1: 'var(--warn)', 2: 'var(--ok)', 3: 'var(--danger)' };

function LoginChart({ series }: { series: Overview['logins']['series'] }) {
  const max = Math.max(1, ...series.map((p) => p.success + p.failed));
  return (
    <div>
      <div className="dash-bars" role="img" aria-label="Successful and failed logins per day, last 14 days">
        {series.map((p) => (
          <div key={p.date} className="dash-bar-col" title={`${formatDate(p.date)}: ${p.success} successful, ${p.failed} failed`}>
            <div className="dash-bar-stack" style={{ height: `${((p.success + p.failed) / max) * 100}%` }}>
              {p.failed > 0 && <div className="dash-bar-failed" style={{ flexGrow: p.failed }} />}
              {p.success > 0 && <div className="dash-bar-ok" style={{ flexGrow: p.success }} />}
            </div>
          </div>
        ))}
      </div>
      <div className="between tiny faint" style={{ marginTop: 6 }}>
        <span>{formatDate(series[0]?.date)}</span><span>Today</span>
      </div>
      <div className="row tiny muted" style={{ marginTop: 10 }}>
        <span className="row-tight"><span className="dot" style={{ background: 'var(--accent)' }} /> Successful</span>
        <span className="row-tight"><span className="dot" style={{ background: 'var(--warn)' }} /> Failed / blocked</span>
      </div>
    </div>
  );
}

function HealthRow({ ok, label, value }: { ok: boolean | null; label: string; value: string }) {
  return (
    <li className="health-row">
      {ok === null ? <span className="dot" style={{ background: 'var(--ink-3)', marginTop: 6 }} />
        : ok ? <CheckCircle2 size={15} style={{ color: 'var(--ok)', flex: 'none' }} />
          : <CircleAlert size={15} style={{ color: 'var(--warn)', flex: 'none' }} />}
      <span className="grow" style={{ minWidth: 0 }}>
        <span className="small" style={{ display: 'block' }}>{label}</span>
        <span className="tiny faint truncate" style={{ display: 'block' }} title={value}>{value}</span>
      </span>
    </li>
  );
}

const WS_KEY = 'tura.admin.dashboard.workspace';

export default function Dashboard() {
  const [workspace, setWorkspace] = useState<string>(() => { try { return localStorage.getItem(WS_KEY) ?? ''; } catch { return ''; } });
  const pick = (v: string) => { setWorkspace(v); try { localStorage.setItem(WS_KEY, v); } catch { /* ignore */ } };
  const orgs = useQuery({
    queryKey: ['admin', 'organisations', 'choices'],
    queryFn: async () => (await api.get<{ organisations: { id: number; name: string; kind: string }[] }>('/api/superadmin/organisations', { params: { status: 'active' } }))
      .data.organisations.filter((o) => o.kind !== 'individual'),
  });
  const ov = useQuery({
    queryKey: ['admin', 'overview', workspace],
    queryFn: async () => (await api.get<Overview>('/api/superadmin/overview', { params: workspace ? { workspace } : {} })).data,
    placeholderData: (prev) => prev,
  });
  const idx = useIndex();
  if (ov.isLoading) return <Loading />;
  if (ov.error) return <ErrorNotice error={ov.error} />;
  const d = ov.data!;
  const stageTotal = Math.max(1, d.documents.total);
  const sent = d.emails.by_status.sent ?? 0;
  const failed = (d.emails.by_status.failed ?? 0) + (d.emails.by_status.error ?? 0);
  const pending = d.emails.by_status.pending ?? 0;

  return (
    <>
      <PageHeader eyebrow="TuraVector administration" title="Dashboard"
        subtitle="An overview of users, documents and system activity."
        actions={
          <label className="ws-switch">
            <span className="ws-switch-label">Workspace</span>
            <select className="input" value={workspace} onChange={(e) => pick(e.target.value)} aria-label="Workspace">
              <option value="">All workspaces</option>
              {(orgs.data ?? []).map((o) => <option key={o.id} value={String(o.id)}>{o.name}</option>)}
            </select>
          </label>
        } />

      <InvoiceApprovals />

      <div className="stat-grid">
        <Stat value={d.users.total} label="Users" note={`${d.users.active} active · ${d.users.new_30d} new in 30 days`} />
        <Stat value={d.documents.total} label="Documents" note={`${d.documents.versions} versions · ${d.documents.new_30d} new in 30 days`} />
        <Stat value={d.library.references} label="References" note={`${d.library.zips} ZIP bundles`} />
        <Stat value={d.library.projects} label="Research projects" />
        <Stat value={d.logins.success_14d} label="Logins (14 days)" note={`${d.logins.failed_14d} failed or blocked`} />
        <Stat value={d.emails.total} label="Emails sent" note={`${failed} failed · ${d.emails.last_30d} in 30 days`} />
      </div>

      <div className="dash-grid" style={{ marginTop: 22 }}>
        <div className="stack-lg">
          <Panel title="Login activity" actions={<Link className="act" to="/authentication/loginlog/">All login logs</Link>}>
            <LoginChart series={d.logins.series} />
          </Panel>

          <div className="grid-2">
            <Panel title="Documents by status" actions={<Link className="act" to="/documents/document/">Open</Link>}>
              <ul className="stage-list">
                {d.documents.by_stage.map((s) => (
                  <li key={s.stage}>
                    <div className="between small"><span>{s.label}</span><strong>{s.count}</strong></div>
                    <div className="meter"><div className="meter-fill" style={{ width: `${(s.count / stageTotal) * 100}%`, background: STAGE_TONE[s.stage] }} /></div>
                  </li>
                ))}
              </ul>
            </Panel>
            <Panel title="Email delivery" actions={<Link className="act" to="/documents/emaillog/">Email logs</Link>}>
              <ul className="stage-list">
                {[['Sent', sent, 'var(--ok)'], ['Failed', failed, 'var(--danger)'], ['Pending', pending, 'var(--warn)']].map(([label, n, c]) => (
                  <li key={label as string}>
                    <div className="between small"><span>{label}</span><strong>{n as number}</strong></div>
                    <div className="meter"><div className="meter-fill" style={{ width: `${((n as number) / Math.max(1, d.emails.total)) * 100}%`, background: c as string }} /></div>
                  </li>
                ))}
              </ul>
            </Panel>
          </div>

          <Panel title="Recent sign-ins" flush actions={<Link className="act" to="/authentication/loginlog/">View all</Link>}>
            <div className="table-scroll">
              <table className="tbl">
                <thead><tr><th>User</th><th>Status</th><th>IP address</th><th>When</th></tr></thead>
                <tbody>
                  {d.logins.recent.map((l) => (
                    <tr key={l.id}>
                      <td><span className="small" style={{ fontWeight: 500 }}>{l.name || l.username}</span>{l.name && <span className="tiny faint" style={{ display: 'block' }}>{l.username}</span>}</td>
                      <td><span className={`status ${l.status === 'success' ? 'status-completed' : 'status-declined'}`}>{l.status === 'success' ? 'Success' : l.status === 'blocked' ? 'Blocked' : 'Failed'}</span></td>
                      <td className="mono">{l.ip}</td>
                      <td className="small" title={formatDateTime(l.time)}>{timeAgo(l.time)}</td>
                    </tr>
                  ))}
                  {d.logins.recent.length === 0 && <tr><td colSpan={4} className="muted small">No sign-ins yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>

        <div className="stack-lg">
          <Panel title="System health" actions={<Link className="act" to="/settings/">Settings</Link>}>
            <ul className="health-list">
              <HealthRow ok label="Database" value={d.health.database} />
              <HealthRow ok={d.health.media_exists} label="Uploaded files" value={d.health.media_exists ? d.health.media_root : `Missing or empty: ${d.health.media_root}`} />
              <HealthRow ok={!!d.health.smtp} label="Outgoing email" value={d.health.smtp ? `SMTP ${d.health.smtp}` : `No active SMTP settings (fallback: ${d.health.email_fallback})`} />
              <HealthRow ok={d.health.pdftron_licensed} label={`PDFTron WebViewer ${d.health.pdftron_version}`} value={d.health.pdftron_licensed ? 'Licensed' : 'No licence key — runs in trial mode'} />
              <HealthRow ok={null} label="OnlyOffice server" value={d.health.onlyoffice_url} />
              <HealthRow ok={!d.health.debug} label="Debug mode" value={d.health.debug ? 'On — turn off for production' : 'Off'} />
            </ul>
          </Panel>

          <Panel title="Users">
            <dl className="kv">
              <dt>Active</dt><dd>{d.users.active} of {d.users.total}</dd>
              <dt>Superusers</dt><dd>{d.users.superusers}</dd>
              <dt>Staff</dt><dd>{d.users.staff}</dd>
              <dt>New (30 days)</dt><dd>{d.users.new_30d}</dd>
            </dl>
            <div className="row wrap" style={{ marginTop: 14 }}>
              <Link className="btn btn-secondary btn-sm" to="/authentication/user/">Manage users</Link>
              <Link className="btn btn-secondary btn-sm" to="/authentication/user/add/"><Plus size={13} /> Add user</Link>
            </div>
          </Panel>

          <Panel title="Recent admin actions">
            {!idx.data || idx.data.recent_actions.length === 0 ? <p className="muted small">None yet.</p> : (
              <ul className="recent-list">
                {idx.data.recent_actions.map((e) => (
                  <li key={e.id}>
                    <ActionFlag e={e} />
                    <span className="grow" style={{ minWidth: 0 }}>
                      {e.link ? <Link className="act" to={adminPath(e.link)}>{e.object_repr}</Link> : <span>{e.object_repr}</span>}
                      <span className="tiny faint" style={{ display: 'block' }}>{e.content_type ? `${e.content_type} · ` : ''}{formatDateTime(e.action_time)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
