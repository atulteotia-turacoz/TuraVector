import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, FileSpreadsheet, FileText } from 'lucide-react';
import { downloadFile } from '@/lib/api';
import { Badge, DataTable, ErrorNotice, Loading, PageHeader, Panel, Stat, useToast, type Column } from '@/components/ui';
import { formatDate } from '@/lib/format';
import { ActiveBadge, DocStatus, truncate, useErrorToast, usePageData, type UserRow } from '../shared';

interface ReportData {
  date_range: string; start_date: string; end_date: string; period_name: string;
  total_documents: number; documents_in_period: number; total_versions: number; versions_in_period: number;
  active_users: number; draft_docs: number; review_docs: number; approved_docs: number; revised_docs: number;
  total_references: number; references_in_period: number;
  recent_documents: { id: number; document_name: string; document_number: string; owner: string; stage_status: number; created_at: string }[];
  recent_users: UserRow[];
  top_users: (UserRow & { document_count: number })[];
}

type Section = 'recent_documents' | 'top_users' | 'recent_users';

/** YYYY-MM-DD of a local day (what <input type="date"> uses). */
const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const daysAgo = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return ymd(d); };

export default function Reports() {
  const [params, setParams] = useSearchParams();
  const dateRange = params.get('date_range') || '30';
  const custom = dateRange === 'custom';
  const dateFrom = params.get('from') || daysAgo(30);
  const dateTo = params.get('to') || ymd(new Date());
  // what every request (page and exports) sends for the chosen period
  const period: Record<string, string> = custom ? { date_range: 'custom', date_from: dateFrom, date_to: dateTo } : { date_range: dateRange };
  const fileTag = custom ? `${dateFrom}_to_${dateTo}` : `${dateRange}days`;
  const [draft, setDraft] = useState({ from: dateFrom, to: dateTo });
  useEffect(() => setDraft({ from: dateFrom, to: dateTo }), [dateFrom, dateTo]);
  const q = usePageData<ReportData>(['reports', dateRange, custom ? dateFrom : '', custom ? dateTo : ''], '/api/users/reports', period);
  const toast = useToast();
  const showError = useErrorToast();
  const [busy, setBusy] = useState<string | null>(null);

  // Auto-refresh every 5 minutes (reports.html reloads the page)
  useEffect(() => {
    const t = setTimeout(() => { void q.refetch(); }, 300000);
    return () => clearTimeout(t);
  }, [q.dataUpdatedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const d = q.data;

  const exportReport = async (format: 'excel' | 'pdf') => {
    setBusy(`report-${format}`);
    try {
      await downloadFile('/api/users/reports/export', { format, ...period },
        `turavector_report_${fileTag}.${format === 'excel' ? 'xlsx' : 'pdf'}`);
      toast.success(`Report exported successfully as ${format.toUpperCase()}`);
    } catch (e) { showError(e); } finally { setBusy(null); }
  };

  const exportSection = async (section: Section, format: 'excel' | 'pdf') => {
    setBusy(`${section}-${format}`);
    try {
      await downloadFile('/api/users/reports/export-section', { section, format, ...period },
        `turavector_${section}_${fileTag}.${format === 'excel' ? 'xlsx' : 'pdf'}`);
      const name = section.replace('_', ' ').replace(/\b\w/g, (l) => l.toUpperCase());
      toast.success(`${name} exported successfully as ${format.toUpperCase()}`);
    } catch (e) { showError(e); } finally { setBusy(null); }
  };

  const sectionButtons = (section: Section) => (
    <>
      <button className="btn btn-ghost btn-icon" title="Export Excel" disabled={!!busy} onClick={() => exportSection(section, 'excel')}><FileSpreadsheet size={14} /></button>
      <button className="btn btn-ghost btn-icon" title="Export PDF" disabled={!!busy} onClick={() => exportSection(section, 'pdf')}><FileText size={14} /></button>
    </>
  );

  const recentUserCols: Column<UserRow>[] = [
    { key: 'name', header: 'Name', value: (u) => `${u.first_name} ${u.last_name}`,
      render: (u) => <span className="row-tight wrap"><strong>{u.first_name} {u.last_name}</strong>{u.is_manager && <Badge tone="accent">Manager</Badge>}</span> },
    { key: 'email', header: 'Email' },
    { key: 'user_type_display', header: 'User Type', render: (u) => <Badge>{u.user_type_display}</Badge> },
    { key: 'is_active', header: 'Status', value: (u) => (u.is_active ? 'Active' : 'Inactive'), render: (u) => <ActiveBadge active={u.is_active} /> },
    { key: 'date_joined', header: 'Joined', value: (u) => u.date_joined || '', render: (u) => formatDate(u.date_joined) },
    { key: 'last_login', header: 'Last Login', value: (u) => u.last_login || '', render: (u) => (u.last_login ? formatDate(u.last_login) : <Badge>Never</Badge>) },
    { key: 'document_count', header: 'Documents', render: (u) => <Badge>{u.document_count ?? 0}</Badge> },
  ];

  return (
    <div className="stack-lg">
      <PageHeader title="Reports & Analytics"
        actions={<Link className="btn btn-secondary" to="/content-lab-management/dashboard/"><ArrowLeft size={14} /> Back to Dashboard</Link>} />

      <Panel title="Report Settings" actions={<>
        <button className="btn btn-secondary btn-sm" disabled={!!busy} onClick={() => exportReport('excel')}><FileSpreadsheet size={14} /> {busy === 'report-excel' ? 'Exporting...' : 'Export Excel'}</button>
        <button className="btn btn-secondary btn-sm" disabled={!!busy} onClick={() => exportReport('pdf')}><FileText size={14} /> {busy === 'report-pdf' ? 'Exporting...' : 'Export PDF'}</button>
      </>}>
        <div className="form-grid">
          <label className="field">
            <span className="field-label">Date Range</span>
            <select className="input" value={dateRange}
              onChange={(e) => setParams(e.target.value === 'custom'
                ? { date_range: 'custom', from: draft.from, to: draft.to } : { date_range: e.target.value })}>
              <option value="7">Last 7 Days</option>
              <option value="30">Last 30 Days</option>
              <option value="90">Last 90 Days</option>
              <option value="365">Last Year</option>
              <option value="custom">Custom range…</option>
            </select>
          </label>
          {custom ? (
            <form className="field" onSubmit={(e) => { e.preventDefault(); setParams({ date_range: 'custom', from: draft.from, to: draft.to }); }}>
              <span className="field-label">From – To</span>
              <div className="rp-range">
                <input className="input" type="date" required value={draft.from} max={draft.to || undefined}
                  onChange={(e) => setDraft((r) => ({ ...r, from: e.target.value }))} aria-label="From date" />
                <span className="muted">to</span>
                <input className="input" type="date" required value={draft.to} min={draft.from || undefined} max={ymd(new Date())}
                  onChange={(e) => setDraft((r) => ({ ...r, to: e.target.value }))} aria-label="To date" />
                <button className="btn btn-primary btn-sm" disabled={!draft.from || !draft.to || (draft.from === dateFrom && draft.to === dateTo)}>Apply</button>
              </div>
            </form>
          ) : (
            <div className="field">
              <span className="field-label">Report Period</span>
              <div><strong>{formatDate(d.start_date)}</strong> to <strong>{formatDate(d.end_date)}</strong></div>
            </div>
          )}
        </div>
      </Panel>

      <div className="stat-grid">
        <Stat value={d.total_documents} label="Total Documents" note={`${d.documents_in_period} in period`} />
        <Stat value={d.total_versions} label="Total Versions" note={`${d.versions_in_period} in period`} />
        <Stat value={d.active_users} label="Active Users" note="in period" />
        <Stat value={d.total_references} label="References" note={`${d.references_in_period} in period`} />
      </div>
      <div className="stat-grid">
        <Stat value={d.draft_docs} label="Draft Documents" />
        <Stat value={d.review_docs} label="Under Review" />
        <Stat value={d.approved_docs} label="Approved" />
        <Stat value={d.revised_docs} label="Needs Revision" />
      </div>

      <div className="grid-2">
        <Panel title="Recent Documents" actions={sectionButtons('recent_documents')} flush>
          {d.recent_documents.length ? (
            <div className="table-scroll"><table className="tbl">
              <thead><tr><th>Document</th><th>Owner</th><th>Status</th><th>Created</th></tr></thead>
              <tbody>{d.recent_documents.map((doc) => (
                <tr key={doc.id}>
                  <td><strong>{truncate(doc.document_name, 30)}</strong><div className="tiny muted">{doc.document_number}</div></td>
                  <td>{doc.owner}</td>
                  <td><DocStatus status={doc.stage_status} variant="short" /></td>
                  <td className="nowrap">{new Date(doc.created_at).toLocaleDateString('en-US', { month: 'short', day: '2-digit' })}</td>
                </tr>
              ))}</tbody>
            </table></div>
          ) : <div className="empty small">No recent documents</div>}
        </Panel>

        <Panel title="Top Users by Documents" actions={sectionButtons('top_users')} flush>
          {d.top_users.length ? (
            <div className="table-scroll"><table className="tbl">
              <thead><tr><th>User</th><th>Type</th><th>Documents</th><th>Status</th></tr></thead>
              <tbody>{d.top_users.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.first_name} {u.last_name}</strong><div className="tiny muted">{u.email}</div></td>
                  <td><Badge>{u.user_type_display}</Badge></td>
                  <td><Badge tone="accent">{u.document_count}</Badge></td>
                  <td><ActiveBadge active={u.is_active} /></td>
                </tr>
              ))}</tbody>
            </table></div>
          ) : <div className="empty small">No user data available</div>}
        </Panel>
      </div>

      <Panel title="Recent Users" actions={sectionButtons('recent_users')}>
        {d.recent_users.length
          ? <DataTable rows={d.recent_users} columns={recentUserCols} rowKey={(u) => u.id} pageSize={10} />
          : <div className="empty"><h3>No recent users</h3></div>}
      </Panel>
    </div>
  );
}
