import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Eye, EyeOff, KeyRound, RotateCw } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { API, formErrors } from '@/lib/admin';
import { Badge, ErrorNotice, Loading, PageHeader, Panel, useConfirm, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

interface SettingItem {
  key: string; type: 'str' | 'bool' | 'int' | 'choice'; is_secret: boolean; read_only: boolean; requires_restart: boolean;
  help: string; is_set: boolean; value: any; choices?: [string, string][]; can_generate?: boolean;
}
interface Section { title: string; keys: SettingItem[] }

const RESTART_STORE = 'tura.admin.restartKeys';
function readRestart(): string[] {
  try { return JSON.parse(sessionStorage.getItem(RESTART_STORE) || '[]'); } catch { return []; }
}

/** 48 random bytes, base64url — a shared signing secret the admin then copies into the other app. */
function generateSecret(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(48));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} aria-label={label} />
      <span className="track" aria-hidden />
      <span className="small muted">{checked ? 'On' : 'Off'}</span>
    </label>
  );
}

function SectionForm({ section, onSaved }: { section: Section; onSaved: (restart: string[]) => void }) {
  const toast = useToast();
  const confirm = useConfirm();
  const editable = section.keys.filter((k) => !k.read_only);
  const initial = () => Object.fromEntries(editable.map((k) => [k.key, k.is_secret ? '' : k.value]));
  const [values, setValues] = useState<Record<string, any>>(initial);
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [cleared, setCleared] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setValues(initial()); setRevealed({}); setCleared({}); setErrors({}); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [section]);

  const reveal = async (key: string) => {
    if (revealed[key]) { setRevealed((r) => ({ ...r, [key]: false })); setValues((v) => ({ ...v, [key]: '' })); return; }
    try {
      const { data } = await api.post(`${API}/settings/${key}/reveal`);
      setValues((v) => ({ ...v, [key]: data.value }));
      setRevealed((r) => ({ ...r, [key]: true }));
      setCleared((c) => ({ ...c, [key]: false }));
    } catch (err) { toast.error(errorMessage(err)); }
  };

  const save = async () => {
    const payload: Record<string, any> = {};
    const toClear: string[] = [];
    for (const k of editable) {
      const v = values[k.key];
      if (k.is_secret) {
        if (cleared[k.key]) toClear.push(k.key);
        else if (v !== '' && v !== undefined) payload[k.key] = v;  // blank keeps the current secret
      } else if (k.type === 'bool') payload[k.key] = !!v;
      else payload[k.key] = v ?? '';
    }
    if (toClear.length) {
      const ok = await confirm({ title: 'Clear secrets?', danger: true, confirmLabel: 'Clear and save',
        message: `This removes the stored value of ${toClear.join(', ')}. Features that rely on it will stop working.` });
      if (!ok) return;
    }
    setBusy(true); setErrors({});
    try {
      // A blank secret means "keep the current value"; an explicit Clear is sent as whitespace, which the API stores as empty.
      toClear.forEach((k) => { payload[k] = ' '; });
      const { data } = await api.put(`${API}/settings`, payload);
      toast.success(data.message);
      onSaved(data.requires_restart || []);
    } catch (err) {
      const fe = formErrors(err) as any;
      if (fe?.errors) setErrors(fe.errors);
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const readOnly = editable.length === 0;
  return (
    <Panel title={section.title} flush
      footer={!readOnly && <div className="row"><button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? 'Saving…' : `Save ${section.title}`}</button></div>}>
      {section.keys.map((k) => {
        const err = errors[k.key];
        let input;
        if (k.read_only) {
          input = <div className="readonly" style={{ paddingTop: 7 }}>{k.is_secret ? (k.is_set ? <Badge tone="ok">Set</Badge> : <Badge tone="warn">Not set</Badge>) : <span className="mono">{String(k.value ?? '')}</span>}</div>;
        } else if (k.type === 'bool') {
          input = <Toggle checked={!!values[k.key]} label={k.key} onChange={(v) => setValues((s) => ({ ...s, [k.key]: v }))} />;
        } else if (k.type === 'choice') {
          input = (
            <select className={`input ${err ? 'error' : ''}`} style={{ maxWidth: 320 }} value={values[k.key] ?? ''} onChange={(e) => setValues((s) => ({ ...s, [k.key]: e.target.value }))}>
              {(k.choices || []).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          );
        } else if (k.is_secret) {
          input = (
            <div className="secret-row">
              <input className={`input ${err ? 'error' : ''}`} type={revealed[k.key] ? 'text' : 'password'} autoComplete="off" spellCheck={false}
                placeholder={cleared[k.key] ? 'Will be cleared on save' : k.is_set ? `${k.value} — leave blank to keep` : 'Not set'}
                value={values[k.key] ?? ''} onChange={(e) => { setCleared((c) => ({ ...c, [k.key]: false })); setValues((s) => ({ ...s, [k.key]: e.target.value })); }} />
              {k.can_generate && <button type="button" className="btn btn-secondary btn-sm" title="Fill in a new random secret (save to apply)"
                onClick={() => { setValues((s) => ({ ...s, [k.key]: generateSecret() })); setRevealed((r) => ({ ...r, [k.key]: true })); setCleared((c) => ({ ...c, [k.key]: false })); }}>
                <KeyRound size={13} /> Generate</button>}
              {k.is_set && <button type="button" className="btn btn-secondary btn-sm" onClick={() => reveal(k.key)}>{revealed[k.key] ? <><EyeOff size={13} /> Hide</> : <><Eye size={13} /> Reveal</>}</button>}
              {k.is_set && <button type="button" className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }} onClick={() => { setValues((s) => ({ ...s, [k.key]: '' })); setRevealed((r) => ({ ...r, [k.key]: false })); setCleared((c) => ({ ...c, [k.key]: true })); }}>Clear</button>}
            </div>
          );
        } else {
          input = <input className={`input ${err ? 'error' : ''}`} type={k.type === 'int' ? 'number' : 'text'} value={values[k.key] ?? ''} spellCheck={false}
            style={k.type === 'int' ? { maxWidth: 220 } : undefined} onChange={(e) => setValues((s) => ({ ...s, [k.key]: e.target.value }))} />;
        }
        return (
          <div key={k.key} className="set-row">
            <div className="set-key">{k.key}{k.requires_restart && <Badge tone="warn">restart</Badge>}{k.is_secret && !k.read_only && <Badge>secret</Badge>}</div>
            <div style={{ minWidth: 0 }}>
              {err && <ul className="errorlist" role="alert">{err.map((x, i) => <li key={i}>{x}</li>)}</ul>}
              {input}
              {k.help && <span className="field-help">{k.help}</span>}
            </div>
          </div>
        );
      })}
    </Panel>
  );
}

export default function SystemSettings() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'settings'], queryFn: async () => (await api.get<{ sections: Section[]; env_file: string }>(`${API}/settings`)).data, staleTime: 0 });
  const [restart, setRestart] = useState<string[]>(readRestart);
  const onSaved = (keys: string[]) => {
    const next = Array.from(new Set([...restart, ...keys])).sort();
    setRestart(next);
    try { sessionStorage.setItem(RESTART_STORE, JSON.stringify(next)); } catch { /* ignore */ }
    void qc.invalidateQueries({ queryKey: ['admin', 'settings'] });
    void qc.invalidateQueries({ queryKey: ['admin', 'index'] });
  };
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  return (
    <>
      <Crumbs items={[{ label: 'System Settings' }]} />
      <PageHeader title="System Settings" subtitle={`Configuration and secrets stored in backend/${q.data!.env_file}.`} />
      <div className="notice notice-warn" role="note" style={{ marginBottom: 16 }}>
        <div className="notice-title row-tight"><AlertTriangle size={14} /> Changes affect the live system</div>
        Saved values are written to the server’s .env file (the previous version is kept as .env.bak) and take effect immediately for every user.
      </div>
      {restart.length > 0 && (
        <div className="notice notice-danger" role="status" style={{ marginBottom: 16 }}>
          <div className="notice-title row-tight"><RotateCw size={14} /> Restart required</div>
          The backend must be restarted before these changes take effect: <span className="mono">{restart.join(', ')}</span>.{' '}
          <button className="act" onClick={() => { setRestart([]); try { sessionStorage.removeItem(RESTART_STORE); } catch { /* ignore */ } }}>Dismiss</button>
        </div>
      )}
      <div className="stack-lg">
        {q.data!.sections.map((s) => <SectionForm key={s.title} section={s} onSaved={onSaved} />)}
      </div>
    </>
  );
}
