import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArcElement, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LinearScale, LineElement, PointElement, Tooltip,
} from 'chart.js';
import { Bar, Doughnut, Line } from 'react-chartjs-2';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Loading, PageHeader, Panel, Stat } from '@/components/ui';
import { cssVar } from './api';
import './tools.css';

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, PointElement, LineElement, Filler, Legend, Tooltip);

interface Analytics {
  total_documents: number; documents_in_period: number; documents_by_status: { stage_status: number; count: number }[];
  total_users: number; active_users_in_period: number;
  total_reviews: number; completed_reviews: number; pending_reviews: number;
  total_journals: number; monthly_uploads: { month: string; count: number }[];
  user_type_distribution: { user_type: string; count: number }[];
  top_uploaders: { id: number; full_name: string; email: string; upload_count: number }[];
  start_date: string; end_date: string; period_label: string; selected_period: string;
}

const PERIOD_OPTIONS = [
  ['7', 'Last 7 days'], ['30', 'Last 30 days'], ['90', 'Last 3 months'], ['180', 'Last 6 months'], ['365', 'Last year'], ['all', 'All time'],
];
const STATUS_LEGEND = ['Draft', 'Under Review', 'Approved', 'Draft Under Revision'];
const capfirst = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/** documents/analytics.html */
export default function AnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const period = params.get('period') || '30';
  const q = useQuery({
    queryKey: ['tools', 'analytics', period],
    queryFn: async () => (await api.get<Analytics>('/api/tools/analytics', { params: { period } })).data,
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  const palette = ['--c5', '--c2', '--c6', '--c4', '--c1', '--c3'].map((v) => cssVar(v));
  const accent = cssVar('--accent');
  const ink2 = cssVar('--ink-2');
  const grid = cssVar('--hairline');
  const axes = {
    x: { ticks: { color: ink2 }, grid: { color: grid } },
    y: { beginAtZero: true, ticks: { stepSize: 1, color: ink2 }, grid: { color: grid } },
  };

  return (
    <div className="stack-lg">
      <PageHeader title="Analytics Dashboard" actions={
        <div className="row">
          <span className="small muted">Time Period:</span>
          <select className="input" style={{ minWidth: 200 }} value={d.selected_period}
            onChange={(e) => { const p = new URLSearchParams(params); p.set('period', e.target.value); setParams(p); }}>
            {PERIOD_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      } subtitle={`${d.period_label} (${formatDate(d.start_date)} - ${formatDate(d.end_date)})`} />

      <div className="grid-4">
        <Stat value={d.total_documents} label="Total Documents" note={`+${d.documents_in_period} in period`} />
        <Stat value={d.total_users} label="Total Users" note={`${d.active_users_in_period} active in period`} />
        <Stat value={d.total_reviews} label="Total Reviews" note={`${d.completed_reviews} completed`} />
        <Stat value={d.total_journals} label="Journals" />
      </div>

      <Panel title="Document Status Distribution">
        <div className="tools-legend">
          {STATUS_LEGEND.map((l, i) => <span key={l}><i className="dot" style={{ background: palette[i] }} />{l}</span>)}
        </div>
        <div className="tools-chart">
          <Doughnut
            data={{
              labels: d.documents_by_status.map((s) => capfirst(String(s.stage_status))),
              datasets: [{ data: d.documents_by_status.map((s) => s.count), backgroundColor: palette, borderColor: cssVar('--card') }],
            }}
            options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { padding: 15, color: ink2, font: { size: 12 } } } } }}
          />
        </div>
      </Panel>

      <Panel title="Monthly Document Uploads">
        <div className="tools-chart">
          <Line
            data={{
              labels: d.monthly_uploads.map((m) => m.month),
              datasets: [{ label: 'Documents Uploaded', data: d.monthly_uploads.map((m) => m.count), borderColor: accent,
                backgroundColor: cssVar('--accent-soft'), tension: 0.1, fill: true }],
            }}
            options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: axes }}
          />
        </div>
      </Panel>

      <Panel title={`Top Document Uploaders (${d.period_label})`} flush>
        {d.top_uploaders.length ? (
          <table className="tbl">
            <thead><tr><th>User</th><th>Email</th><th>Documents Uploaded</th></tr></thead>
            <tbody>
              {d.top_uploaders.map((u) => (
                <tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td><span className="badge badge-accent">{u.upload_count}</span></td></tr>
              ))}
            </tbody>
          </table>
        ) : <p className="panel-body muted">No document uploads in the selected period.</p>}
      </Panel>

      <Panel title="User Type Distribution">
        <div className="tools-chart">
          <Bar
            data={{
              labels: d.user_type_distribution.map((u) => capfirst(u.user_type)),
              datasets: [{ label: 'Users', data: d.user_type_distribution.map((u) => u.count), backgroundColor: palette.slice(0, 4), borderWidth: 0 }],
            }}
            options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: axes }}
          />
        </div>
      </Panel>
    </div>
  );
}
