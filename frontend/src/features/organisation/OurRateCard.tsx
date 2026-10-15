/** Dashboard panel for a university / organisation admin: the rates Turacoz charges the workspace. */
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { Panel } from '@/components/ui';
import './organisation.css';

interface Rate { id: number; name: string; description: string; unit_label: string; rate: number; tax_percent: number; currency: string; notes: string }

const money = (v: number, currency: string) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency, minimumFractionDigits: 2 }).format(v);

export function OurRateCard() {
  const { user } = useAuth();
  const q = useQuery({
    queryKey: ['org', 'rate-card'],
    queryFn: async () => (await api.get('/api/org/rate-card')).data.items as Rate[],
    enabled: !!user?.is_org_admin,
  });
  if (!user?.is_org_admin || !q.data) return null;
  return (
    <Panel title="Your rate card" flush>
      {q.data.length === 0 ? (
        <div className="panel-body small muted">Your rate card has not been set up yet. Your Turacoz point of contact can help.</div>
      ) : (
        <div className="table-scroll">
          <table className="tbl">
            <thead><tr><th>Service</th><th>Unit</th><th className="num">Rate</th><th className="num">Tax</th></tr></thead>
            <tbody>
              {q.data.map((r) => (
                <tr key={r.id}>
                  <td><div className="org-name">{r.name}</div>{(r.notes || r.description) && <div className="tiny faint">{r.notes || r.description}</div>}</td>
                  <td className="small">{r.unit_label || <span className="faint">—</span>}</td>
                  <td className="num"><strong>{money(r.rate, r.currency)}</strong></td>
                  <td className="num small">{r.tax_percent}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
