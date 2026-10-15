/**
 * Application Access — which dashboard-selection cards each user sees.
 * Set per user (Visible / Hidden); roles don't decide cards. Superusers always see every card,
 * managers always see Content Lab.
 */
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Search } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { ErrorNotice, Loading, PageHeader, Pagination, useConfirm, useToast } from '@/components/ui';
import { Crumbs, ScopeBanner } from '@/components/Shell';
import { LOCK_TEXT, VisibilitySwitch, type CardCell } from '@/components/CardAccessPanel';

interface Resp {
  cards: { key: string; name: string; kind: 'dashboard' | 'app'; url: string | null }[];
  users: {
    items: { id: number; name: string; username: string; email: string; is_superuser: boolean; cards: Record<string, CardCell> }[];
    total: number; page: number; pages: number;
  };
}

export default function AppAccess() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ['admin', 'app-access', term, page],
    queryFn: async () => (await api.get<Resp>('/api/superadmin/app-access', { params: { search: term, page } })).data,
    placeholderData: (prev) => prev,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin'] });

  const setOne = async (userId: number, card: string, visible: boolean) => {
    setBusy(`${userId}:${card}`);
    try {
      const { data } = await api.post('/api/superadmin/app-access/user', { user_id: userId, card, visible });
      toast.success(data.message);
      await refresh();
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(null); }
  };
  const setAll = async (card: { key: string; name: string }, visible: boolean) => {
    const ok = await confirm({
      title: `${visible ? 'Show' : 'Hide'} ${card.name} for everyone`,
      message: `This sets ${card.name} to ${visible ? 'Visible' : 'Hidden'} for every active user. You can still change individual users afterwards.`,
      confirmLabel: visible ? 'Show for everyone' : 'Hide for everyone', danger: !visible,
    });
    if (!ok) return;
    setBusy(`all:${card.key}`);
    try {
      const { data } = await api.post('/api/superadmin/app-access/bulk', { card: card.key, visible });
      toast.success(data.message);
      await refresh();
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(null); }
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  return (
    <>
      <Crumbs items={[{ label: 'Application Access' }]} />
      <PageHeader title="Application Access"
        subtitle="Choose, for each user, which cards they see on the dashboard-selection page. Superusers always see every card; managers always see Content Lab." />
      <ScopeBanner scope="workspace" />

      <section className="panel">
        <div className="panel-head aa-head">
          <h2>Users <span className="faint small">({d.users.total})</span></h2>
          <form className="search-input" onSubmit={(e) => { e.preventDefault(); setTerm(search.trim()); setPage(1); }}>
            <Search size={14} />
            <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, username or email…" aria-label="Search users" />
          </form>
        </div>
        <div className="table-scroll">
          <table className="tbl aa-table">
            <thead>
              <tr>
                <th>User</th>
                {d.cards.map((c) => (
                  <th key={c.key}>
                    {c.url ? <a className="row-tight" href={c.url} target="_blank" rel="noreferrer">{c.name} <ExternalLink size={11} /></a> : c.name}
                    <span className="aa-bulk">
                      <button type="button" className="act" disabled={busy === `all:${c.key}`} onClick={() => void setAll(c, true)}>All on</button>
                      <button type="button" className="act" disabled={busy === `all:${c.key}`} onClick={() => void setAll(c, false)}>All off</button>
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.users.items.map((u) => (
                <tr key={u.id}>
                  <td className="aa-user">
                    <span className="aa-name">{u.name}</span>
                    <span className="aa-sub">{u.email || u.username}</span>
                  </td>
                  {d.cards.map((c) => {
                    const cell = u.cards[c.key];
                    return (
                      <td key={c.key}>
                        <VisibilitySwitch on={cell.visible} disabled={cell.locked || busy === `${u.id}:${c.key}`}
                          label={`${c.name} for ${u.name}`} onChange={(v) => void setOne(u.id, c.key, v)} />
                        {cell.locked && <span className="aa-state is-on">{LOCK_TEXT[cell.source]}</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
              {d.users.items.length === 0 && <tr><td colSpan={d.cards.length + 1} className="muted">No users match.</td></tr>}
            </tbody>
          </table>
        </div>
        <Pagination page={d.users.page} pages={d.users.pages} total={d.users.total} onChange={setPage} />
      </section>
    </>
  );
}
