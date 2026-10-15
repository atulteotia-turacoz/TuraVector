import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Check, Clock, Info, LocateFixed, LogOut, Save, TriangleAlert } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { ThemePicker } from '@/components/ThemePicker';
import { WorkspaceLogo } from '@/components/WorkspaceLogo';
import { Field, Modal, Spinner, useToast } from '@/components/ui';
import { apiError } from './utils';
import './auth.css';

/* ------------------------------------------------------------------ bare page frame */
export function BareFrame({ title, right, children, footer = true, theme = true }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; footer?: boolean; theme?: boolean;
}) {
  return (
    <div className="au-bare">
      <header className="au-topbar">
        <WorkspaceLogo />
        {title && <h4 className="au-hide-sm">{title}</h4>}
        <div className="row">{right}{theme && <ThemePicker />}</div>
      </header>
      <main className="au-bare-main">{children}</main>
      {footer && <LegalFooter />}
    </div>
  );
}

export function LegalFooter() {
  return (
    <footer className="au-bare-footer">
      <span>© 2024 TuraVector. All rights reserved.</span>
      <span className="row">
        <Link to="/documents/terms-and-conditions/">Terms and Conditions</Link>
        <Link to="/documents/privacy-policy/">Privacy Policy</Link>
      </span>
    </footer>
  );
}

export function BackButton({ label = 'Back', className = 'btn btn-secondary btn-sm' }: { label?: string; className?: string }) {
  const navigate = useNavigate();
  return <button type="button" className={className} onClick={() => navigate(-1)}><ArrowLeft size={14} /> {label}</button>;
}

export function LogoutButton() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  return (
    <button type="button" className="btn btn-secondary btn-sm" onClick={async () => { await logout(); navigate('/'); }}>
      <LogOut size={14} /> Logout
    </button>
  );
}

/* ------------------------------------------------------------------ change password */
/**
 * Change-password modal of profile.html ("main") and other_documents_profile.html ("other").
 * The two templates used slightly different messages; both are kept.
 */
export function ChangePasswordModal({ open, onClose, variant }: { open: boolean; onClose: () => void; variant: 'main' | 'other' }) {
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const reset = () => { setCurrent(''); setNext(''); setConfirm(''); };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) { toast.error(variant === 'main' ? 'New passwords do not match' : 'Passwords do not match'); return; }
    if (next.length < 8) { toast.error('Password must be at least 8 characters long'); return; }
    setBusy(true);
    try {
      await api.post('/api/auth/change-password', { current_password: current, new_password: next });
      toast.success('Password changed successfully!');
      reset();
      onClose();
    } catch (err) {
      const msg = apiError(err);
      if (variant === 'main') toast.error(msg ? `Error: ${msg}` : 'An error occurred while changing password');
      else toast.error(msg || 'Error changing password');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Change Password">
      <form className="stack" onSubmit={submit} id="changePasswordForm">
        <Field label="Current Password"><input className="input" type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" /></Field>
        <Field label="New Password" help="Password must be at least 8 characters long"><input className="input" type="password" required value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></Field>
        <Field label="Confirm New Password"><input className="input" type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" /></Field>
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : null}Change Password</button>
        </div>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ timezone selector */
interface TzOption { value: string; label: string; offset: string }

/** Port of templates/timezone_selector.html. */
export function TimezoneSelector() {
  const { user, refresh } = useAuth();
  const [selected, setSelected] = useState('');
  const [original, setOriginal] = useState('');
  const [status, setStatus] = useState<{ type: 'info' | 'success' | 'danger'; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [now, setNow] = useState(() => new Date());

  const tzQuery = useQuery({
    queryKey: ['auth', 'timezones'],
    queryFn: async () => (await api.get('/api/auth/timezones')).data.timezones as TzOption[],
    staleTime: Infinity,
  });
  const infoQuery = useQuery({
    queryKey: ['auth', 'timezone-info'],
    queryFn: async () => (await api.get('/api/auth/timezone-info')).data as { current_timezone: string; timezone_offset: string },
    staleTime: Infinity,
  });
  const [currentName, setCurrentName] = useState<string | null>(null);

  // Once the list is loaded, preselect the user's timezone (or the browser-detected one when anonymous)
  useEffect(() => {
    if (!tzQuery.data) return;
    let initial = '';
    if (user && user.timezone) initial = user.timezone;
    else { try { initial = sessionStorage.getItem('userTimezone') || ''; } catch { /* ignore */ } }
    setOriginal(initial);
    setSelected(initial);
  }, [tzQuery.data, user]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (status?.type !== 'success') return;
    const id = window.setTimeout(() => setStatus(null), 3000);
    return () => window.clearTimeout(id);
  }, [status]);

  const options = tzQuery.data ?? [];
  const inList = options.some((o) => o.value === selected);
  const selectValue = inList ? selected : '';

  let localTime: string;
  try {
    localTime = new Intl.DateTimeFormat('en-US', {
      weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
      timeZoneName: 'short', ...(selectValue ? { timeZone: selectValue } : {}),
    }).format(now);
  } catch {
    localTime = now.toLocaleString();
  }

  const detect = () => {
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (detected) {
      setSelected(detected);
      setStatus({ type: 'success', message: `Timezone detected: ${detected}` });
    }
  };

  const save = async () => {
    if (!selectValue) return;
    setStatus({ type: 'info', message: 'Saving timezone...' });
    setSaving(true);
    try {
      const url = user ? '/api/auth/set-timezone' : '/api/auth/detect-timezone';
      const { data } = await api.post(url, { timezone: selectValue });
      if (data.message) {
        setStatus({ type: 'success', message: data.message });
        setOriginal(selectValue);
        setCurrentName(selectValue);
        // Django reloaded the page after 1.5s to apply the change
        window.setTimeout(() => { void refresh(); setCurrentName(null); }, 1500);
      } else {
        setStatus({ type: 'danger', message: data.error || 'Error saving timezone' });
      }
    } catch (err) {
      setStatus({ type: 'danger', message: apiError(err) || 'Error saving timezone' });
    } finally {
      setSaving(false);
    }
  };

  const saveDisabled = saving || !selectValue || selectValue === original;

  return (
    <div className="stack">
      <div className="au-tz">
        <Field label="Select Your Timezone:" help={<><Info size={12} /> This will be used to display all dates and times in your local timezone.</>}>
          <select className="input" value={selectValue} onChange={(e) => setSelected(e.target.value)} name="timezone">
            {tzQuery.isLoading && <option value="">Loading timezones...</option>}
            {tzQuery.isError && <option value="">Error loading timezones</option>}
            {tzQuery.data && <option value="">Select a timezone...</option>}
            {options.map((tz) => <option key={tz.value} value={tz.value}>{`${tz.label} (${tz.offset})`}</option>)}
          </select>
        </Field>
        <div>
          <div className="field-label" style={{ marginBottom: 6 }}>Current Timezone:</div>
          <div className="well">
            <div className="row-tight" style={{ fontWeight: 600 }}><Clock size={14} /> <span>{currentName ?? infoQuery.data?.current_timezone ?? '…'}</span></div>
            <div className="small muted">Offset: {infoQuery.data?.timezone_offset ?? '…'}</div>
            <div className="small muted au-tz-time">{localTime}</div>
          </div>
        </div>
      </div>
      <div className="between wrap">
        <button type="button" className="btn btn-secondary" onClick={detect}><LocateFixed size={14} /> Auto-Detect My Timezone</button>
        <button type="button" className="btn btn-primary" onClick={save} disabled={saveDisabled}><Save size={14} /> Save Timezone</button>
      </div>
      {status && (
        <div className={`notice notice-${status.type === 'success' ? 'ok' : status.type === 'danger' ? 'danger' : 'accent'}`}>
          <span className="row-tight">
            {status.type === 'success' ? <Check size={14} /> : status.type === 'danger' ? <TriangleAlert size={14} /> : <Info size={14} />}
            {status.message}
          </span>
        </div>
      )}
    </div>
  );
}
