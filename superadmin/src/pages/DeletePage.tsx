import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, errorMessage } from '@/lib/api';
import { API, useModelConfig, type DeleteSummary } from '@/lib/admin';
import { ErrorNotice, Loading, PageHeader, Panel, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';
import { DeleteSummaryView } from '@/components/DeleteSummary';

function capfirst(s: string) { return s ? s[0].toUpperCase() + s.slice(1) : s; }

export default function DeletePage() {
  const { app = '', model = '', pk = '' } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const cfg = useModelConfig(app, model);
  const q = useQuery({
    queryKey: ['admin', 'delete', app, model, pk],
    queryFn: async () => (await api.get<{ pk: string; str: string; summary: DeleteSummary }>(`${API}/models/${app}/${model}/${encodeURIComponent(pk)}/delete`)).data,
    gcTime: 0,
  });
  const [busy, setBusy] = useState(false);
  if (q.isLoading || cfg.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  if (cfg.error) return <ErrorNotice error={cfg.error} />;
  const c = cfg.data!;
  const d = q.data!;
  const doDelete = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete(`${API}/models/${app}/${model}/${encodeURIComponent(pk)}`);
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin'] });
      navigate(`/${app}/${model}/`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Crumbs items={[
        { label: c.app_name, to: `/${app}/` },
        { label: capfirst(c.verbose_name_plural), to: `/${app}/${model}/` },
        { label: d.str, to: `/${app}/${model}/${encodeURIComponent(pk)}/change/` },
        { label: 'Delete' },
      ]} />
      <PageHeader title="Are you sure?" />
      <Panel>
        <DeleteSummaryView summary={d.summary}
          intro={`Are you sure you want to delete the ${c.verbose_name} “${d.str}”? All of the following related items will be deleted:`}
          protectedIntro={`Deleting the ${c.verbose_name} “${d.str}” would require deleting the following protected related objects:`} />
      </Panel>
      <div className="submit-row">
        {!d.summary.protected.length && <button className="btn btn-danger" disabled={busy} onClick={doDelete}>Yes, I’m sure</button>}
        <Link className="btn btn-secondary" to={`/${app}/${model}/${encodeURIComponent(pk)}/change/`}>No, take me back</Link>
      </div>
    </>
  );
}
