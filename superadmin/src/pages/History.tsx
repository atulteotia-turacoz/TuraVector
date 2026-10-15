import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { API, useModelConfig, type LogEntry } from '@/lib/admin';
import { formatDateTime } from '@/lib/format';
import { ErrorNotice, Loading, PageHeader, Panel } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

function capfirst(s: string) { return s ? s[0].toUpperCase() + s.slice(1) : s; }

export default function History() {
  const { app = '', model = '', pk = '' } = useParams();
  const cfg = useModelConfig(app, model);
  const q = useQuery({
    queryKey: ['admin', 'history', app, model, pk],
    queryFn: async () => (await api.get<{ pk: string; str: string; entries: LogEntry[] }>(`${API}/models/${app}/${model}/${encodeURIComponent(pk)}/history`)).data,
  });
  if (q.isLoading || cfg.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  if (cfg.error) return <ErrorNotice error={cfg.error} />;
  const c = cfg.data!;
  const d = q.data!;
  return (
    <>
      <Crumbs items={[
        { label: c.app_name, to: `/${app}/` },
        { label: capfirst(c.verbose_name_plural), to: `/${app}/${model}/` },
        { label: d.str, to: `/${app}/${model}/${encodeURIComponent(pk)}/change/` },
        { label: 'History' },
      ]} />
      <PageHeader title={`Change history: ${d.str}`} />
      <Panel flush>
        {d.entries.length === 0 ? (
          <p className="panel-body muted">This object doesn’t have a change history. It probably wasn’t added via this admin site.</p>
        ) : (
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th scope="col">Date/time</th><th scope="col">User</th><th scope="col">Action</th></tr></thead>
              <tbody>
                {d.entries.map((e) => (
                  <tr key={e.id}>
                    <th scope="row" style={{ textTransform: 'none', letterSpacing: 0, fontSize: 13.5, fontWeight: 400, color: 'var(--ink)', whiteSpace: 'nowrap' }}>{formatDateTime(e.action_time)}</th>
                    <td>{e.user.username}{e.user.full_name ? ` (${e.user.full_name})` : ''}</td>
                    <td>{e.change_message || (e.is_deletion ? 'Deleted.' : '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
