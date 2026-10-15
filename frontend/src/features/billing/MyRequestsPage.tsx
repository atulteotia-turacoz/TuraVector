/** A member's own service requests and how far billing has got (amounts are with the administrator). */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Badge, Empty, ErrorNotice, Loading, PageHeader } from '@/components/ui';
import './billing.css';

interface Req {
  id: number; created_at: string | null; document_id: number | null; document: string | null; document_number: string | null;
  requirement: string; status: string; services: { name: string; unit_label: string; quantity: number }[];
}

export default function MyRequestsPage() {
  const q = useQuery({ queryKey: ['billing', 'my-requests'], queryFn: async () => (await api.get<{ requests: Req[] }>('/api/billing/my-requests')).data });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const reqs = q.data.requests;
  return (
    <>
      <PageHeader title="My service requests" subtitle="Services you asked Turacoz for when submitting a document."
        actions={<Link className="btn btn-primary" to="/content-lab-management/upload/">New submission</Link>} />
      {reqs.length === 0 ? <Empty title="No requests yet">Choose services when you upload a document or write your text.</Empty> : (
        <section className="panel">
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th>Document</th><th>Services</th><th>Requested</th><th>Status</th></tr></thead>
              <tbody>
                {reqs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.document_id ? <Link className="act" to={`/content-lab-management/document/${r.document_id}/`}>{r.document}</Link> : '—'}
                      {r.document_number && <div className="tiny faint mono">{r.document_number}</div>}
                      {r.requirement && <div className="tiny faint inv-req">{r.requirement}</div>}</td>
                    <td className="small">{r.services.map((s) => <div key={s.name}>{s.name}{s.quantity !== 1 && ` × ${s.quantity}`}</div>)}</td>
                    <td className="small nowrap">{r.created_at ? formatDate(r.created_at) : ''}</td>
                    <td><Badge tone={r.status === 'Paid' ? 'ok' : r.status === 'Cancelled' ? 'danger' : undefined}>{r.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
