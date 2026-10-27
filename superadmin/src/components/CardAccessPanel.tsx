/**
 * Which dashboard-selection cards one user sees. Set per user (Visible / Hidden) — roles don't decide cards.
 * Superusers always see every card; managers always see Content Review.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LayoutGrid } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Loading, useToast } from '@/components/ui';

export interface CardCell { visible: boolean; source: 'superuser' | 'manager' | 'visible' | 'hidden'; locked: boolean }
interface Card extends CardCell { key: string; name: string; kind: 'dashboard' | 'app' }

export const LOCK_TEXT: Record<string, string> = {
  superuser: 'Always visible for superusers',
  manager: 'Managers always see Content Review',
};

/** On/off switch used for card visibility. */
export function VisibilitySwitch({ on, disabled, label, onChange }: { on: boolean; disabled?: boolean; label: string; onChange: (v: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled}
      className={`vs ${on ? 'is-on' : ''}`} onClick={() => onChange(!on)}>
      <span className="vs-track"><span className="vs-thumb" /></span>
      <span className="vs-text">{on ? 'Visible' : 'Hidden'}</span>
    </button>
  );
}

export function CardAccessPanel({ userId }: { userId: number }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ['admin', 'card-access', userId],
    queryFn: async () => (await api.get<{ cards: Card[] }>(`/api/superadmin/app-access/users/${userId}`)).data,
  });

  const set = async (card: string, visible: boolean) => {
    setBusy(card);
    try {
      const { data } = await api.post('/api/superadmin/app-access/user', { user_id: userId, card, visible });
      toast.success(data.message);
      await qc.invalidateQueries();
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(null); }
  };

  const groups: { title: string; kind: Card['kind'] }[] = [
    { title: 'TuraVector dashboards', kind: 'dashboard' },
    { title: 'Other Tura applications', kind: 'app' },
  ];

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="row-tight"><LayoutGrid size={15} /> Dashboard cards</h2>
        <Link className="act small" to="/app-access/">All users</Link>
      </div>
      <div className="panel-body">
        {q.isLoading || !q.data ? <Loading /> : (
          <>
            <p className="small muted" style={{ marginBottom: 12 }}>Cards this user sees on the dashboard-selection page.</p>
            {groups.map((g) => (
              <div key={g.kind} className="ca-group">
                <div className="ca-group-title">{g.title}</div>
                {q.data.cards.filter((c) => c.kind === g.kind).map((c) => (
                  <div key={c.key} className="ca-row">
                    <span className="grow" style={{ minWidth: 0 }}>
                      <span className="ca-name">{c.name}</span>
                      {c.locked && <span className="aa-state is-on">{LOCK_TEXT[c.source]}</span>}
                    </span>
                    <VisibilitySwitch on={c.visible} disabled={c.locked || busy === c.key} label={c.name} onChange={(v) => void set(c.key, v)} />
                  </div>
                ))}
              </div>
            ))}
          </>
        )}
      </div>
    </section>
  );
}
