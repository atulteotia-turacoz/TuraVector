import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Info } from 'lucide-react';
import { api } from '@/lib/api';
import { API } from '@/lib/admin';
import { Badge, ErrorNotice, Loading, PageHeader, Panel, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

interface Overview { current_timezone: string; timezone_offset: string; current_system_timezone: string; django_timezone: string; use_tz: boolean }
interface Stats { stats: { timezone: string; count: number; percentage: number }[]; total_users: number; unique_timezones: number }
interface Tz { value: string; label: string; offset: string }

/** templates/admin/timezone_management.html */
export default function Timezone() {
  const toast = useToast();
  const confirm = useConfirm();
  const ov = useQuery({ queryKey: ['admin', 'tz'], queryFn: async () => (await api.get<Overview>(`${API}/timezone`)).data });
  const stats = useQuery({ queryKey: ['admin', 'tz-stats'], queryFn: async () => (await api.get<Stats>(`${API}/timezone/stats`)).data });
  const tzs = useQuery({ queryKey: ['admin', 'tz-all'], queryFn: async () => (await api.get<{ timezones: Tz[] }>(`${API}/timezone/timezones`, { params: { all: true } })).data.timezones, staleTime: Infinity });
  const [def, setDef] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  if (ov.isLoading) return <Loading />;
  if (ov.error) return <ErrorNotice error={ov.error} />;
  const o = ov.data!;
  const options = (tzs.data ?? []).map((t) => <option key={t.value} value={t.value}>{`${t.label} (${t.offset})`}</option>);

  const bulk = async () => {
    if (!from || !to) { toast.warning('Please select both source and destination timezones.'); return; }
    if (from === to) { toast.warning('Source and destination timezones cannot be the same.'); return; }
    const ok = await confirm({ title: 'Bulk update users', message: `Are you sure you want to update all users from ${from} to ${to}? This action cannot be undone.`, confirmLabel: 'Update' });
    if (!ok) return;
    // The original page stops here too: no bulk endpoint was ever implemented in Django.
    toast.info('Bulk update functionality would be implemented via admin API endpoint.');
  };

  return (
    <>
      <Crumbs items={[{ label: 'Timezone Management' }]} />
      <PageHeader title="Timezone Management" actions={<Badge tone="accent">Current System Time: {o.current_timezone} ({o.timezone_offset})</Badge>} />
      <div className="grid-2" style={{ marginBottom: 18 }}>
        <Panel title="System Timezone Configuration">
          <div className="notice notice-accent" style={{ marginBottom: 14 }}>
            <div className="row-tight"><Info size={14} /><strong>Current System Timezone:</strong> {o.current_system_timezone}</div>
            <div><strong>Django TIME_ZONE Setting:</strong> {o.django_timezone}</div>
            <div><strong>USE_TZ Setting:</strong> {o.use_tz ? 'Enabled' : 'Disabled'}</div>
          </div>
          <label className="field">
            <span className="field-label">Default Timezone for New Users:</span>
            <select className="input" value={def} onChange={(e) => setDef(e.target.value)}>
              <option value="">{tzs.isLoading ? 'Loading...' : 'Select timezone...'}</option>{options}
            </select>
          </label>
          {/* As in the Django template, this button has no server action; the default lives in System Settings → TIME_ZONE. */}
          <button type="button" className="btn btn-primary" style={{ marginTop: 14 }}>Update Default Timezone</button>
        </Panel>
        <Panel title="User Timezone Distribution">
          {stats.isLoading ? <Loading /> : stats.error ? <p className="small" style={{ color: 'var(--danger)' }}>Error loading timezone statistics.</p> :
            stats.data!.stats.length === 0 ? <p className="muted">No timezone data available.</p> : (
              <div>
                {stats.data!.stats.map((s) => {
                  const pct = stats.data!.total_users ? ((s.count / stats.data!.total_users) * 100).toFixed(1) : '0.0';
                  return (
                    <div key={s.timezone} className="tz-stat">
                      <div className="between small"><span><strong>{s.timezone}</strong> <span className="muted">({s.count} users)</span></span><Badge tone="accent">{pct}%</Badge></div>
                      <div className="meter" role="img" aria-label={`${pct}%`}><div className="meter-fill" style={{ width: `${pct}%` }} /></div>
                    </div>
                  );
                })}
              </div>
            )}
        </Panel>
      </div>
      <Panel title="Bulk Timezone Operations">
        <div className="grid-3">
          <label className="field"><span className="field-label">From Timezone:</span>
            <select className="input" value={from} onChange={(e) => setFrom(e.target.value)}><option value="">Select timezone...</option>{options}</select></label>
          <label className="field"><span className="field-label">To Timezone:</span>
            <select className="input" value={to} onChange={(e) => setTo(e.target.value)}><option value="">Select timezone...</option>{options}</select></label>
          <div className="field"><span className="field-label">&nbsp;</span><button type="button" className="btn btn-secondary" onClick={bulk}>Bulk Update Users</button></div>
        </div>
        <div className="notice notice-warn" style={{ marginTop: 14 }}>
          <span className="row-tight"><AlertTriangle size={14} /><strong>Warning:</strong> Bulk timezone updates will affect multiple users. Use with caution.</span>
        </div>
      </Panel>
      <div style={{ marginTop: 18 }}>
        <Panel title="Recent Timezone Changes" flush>
          <div className="table-scroll">
            <table className="tbl">
              <thead><tr><th>User</th><th>Email</th><th>Previous Timezone</th><th>New Timezone</th><th>Changed At</th><th>Actions</th></tr></thead>
              <tbody><tr><td colSpan={6} className="center muted small">No timezone change history is recorded.</td></tr></tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
  );
}
