import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, BookOpen, CalendarDays, FileOutput, LineChart, Search, Users } from 'lucide-react';
import type { ReactNode } from 'react';
import { api } from '@/lib/api';
import { ErrorNotice, Loading, PageHeader, Panel } from '@/components/ui';
import './tools.css';

interface Dashboard {
  saved_journals_count: number;
}

function Card({ icon, title, text, stats, action }: { icon: ReactNode; title: string; text: string; stats: [number, string][]; action: ReactNode }) {
  return (
    <Panel title={<span className="row-tight">{icon} {title}</span>}>
      <p className="muted">{text}</p>
      <div className="tools-card-stats">
        {stats.map(([v, l]) => <div key={l} className="stat" style={{ border: 0, padding: 0 }}><div className="stat-value">{v}</div><div className="stat-label">{l}</div></div>)}
      </div>
      {action}
    </Panel>
  );
}

/** documents/other_documents_dashboard.html */
export default function OtherDocumentsDashboardPage() {
  const q = useQuery({
    queryKey: ['tools', 'other-documents'],
    queryFn: async () => (await api.get<Dashboard>('/api/tools/other-documents')).data,
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  return (
    <div className="stack-lg">
      <PageHeader eyebrow="Other Document Types Dashboard" title="Welcome to Other Document Types"
        subtitle="Find journals and conferences for your research, and track your activity" />
      <div className="grid-3">
        <Card icon={<BookOpen size={16} />} title="Journal Selector" text="Find and select appropriate journals for your research publications."
          stats={[[d.saved_journals_count, 'Saved Journals'], [0, 'Submissions']]}
          action={<Link className="btn btn-primary" to="/journal-selector/journals/"><Search size={14} /> Find Journals</Link>} />
        <Card icon={<Users size={16} />} title="Conference Selector" text="Discover and track conferences relevant to your research area."
          stats={[[0, 'Tracked Conferences'], [0, 'Submissions']]}
          action={<button className="btn btn-primary" disabled><CalendarDays size={14} /> Browse Conferences</button>} />
        <Card icon={<LineChart size={16} />} title="Analytics" text="View comprehensive analytics and insights for your research activities."
          stats={[[0, 'Total Documents'], [0, 'This Month']]}
          action={<button className="btn btn-primary" disabled><BarChart3 size={14} /> View Analytics</button>} />
      </div>
      <Panel title="Quick Actions">
        <div className="tools-actions-grid">
          <Link to="/journal-selector/journals/"><Search size={20} /><span>Search Journals</span></Link>
          <Link to="/journal-selector/export-data/"><FileOutput size={20} /><span>Export Data</span></Link>
        </div>
      </Panel>
    </div>
  );
}
