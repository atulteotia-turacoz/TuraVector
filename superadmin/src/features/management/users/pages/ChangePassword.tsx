import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Check, Eye, EyeOff, Save, X } from 'lucide-react';
import { api } from '@/lib/api';
import { ErrorNotice, Field, Loading, PageHeader, Panel } from '@/components/ui';
import { apiError, useFlash, usePageData, type ActionResult, type UserRow } from '../shared';
import { PasswordMeter } from '../components/PasswordMeter';

const REQUIREMENTS: { key: string; label: string; test: (p: string) => boolean }[] = [
  { key: 'length', label: 'At least 8 characters long', test: (p) => p.length >= 8 },
  { key: 'uppercase', label: 'Contains uppercase letter (A-Z)', test: (p) => /[A-Z]/.test(p) },
  { key: 'lowercase', label: 'Contains lowercase letter (a-z)', test: (p) => /[a-z]/.test(p) },
  { key: 'number', label: 'Contains number (0-9)', test: (p) => /[0-9]/.test(p) },
  { key: 'special', label: 'Contains special character (!@#$%^&*)', test: (p) => /[^a-zA-Z0-9]/.test(p) },
];

export default function ChangePassword() {
  const { userId } = useParams();
  const q = usePageData<{ page_title: string; target_user: UserRow }>(['change-password', userId], `/api/users/${userId}/change-password`);
  const navigate = useNavigate();
  const flash = useFlash();
  const [v, setV] = useState({ new_password: '', confirm_password: '', send_email: true, force_change: true });
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const t = q.data.target_user;
  const fullName = `${t.first_name} ${t.last_name}`.trim();

  const met = REQUIREMENTS.map((r) => r.test(v.new_password));
  const allMet = met.every(Boolean);
  const matches = !!v.confirm_password && v.new_password === v.confirm_password;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!allMet) { setErrors(['Please ensure the password meets all requirements.']); return; }
    if (!matches) { setErrors(['Passwords do not match.']); return; }
    setBusy(true);
    try {
      const { data } = await api.post<ActionResult>(`/api/users/${t.id}/change-password`, v);
      flash(data.messages, data.message);
      navigate('/library/manage-users/');
    } catch (err) {
      setErrors(apiError(err).messages);
    } finally { setBusy(false); }
  };

  return (
    <div className="page-narrow stack-lg" style={{ padding: 0 }}>
      <PageHeader title="Change User Password"
        actions={<>
          <Link className="btn btn-secondary" to="/library/manage-users/"><ArrowLeft size={14} /> Back to All Users</Link>
          <Link className="btn btn-secondary" to={`/library/user/${t.id}/view/`}><Eye size={14} /> View Profile</Link>
        </>} />

      <Panel>
        <h3 style={{ margin: 0 }}>{fullName}</h3>
        <div className="muted small">{t.email}</div>
        <div className="small">{t.user_type_display}{t.is_manager && ' | Manager'}</div>
      </Panel>

      <div className="notice notice-warn">
        <div className="notice-title">Security Notice</div>
        You are about to change the password for this user. The new password will be sent to their email address,
        and they will be required to change it on their next login for security purposes.
      </div>

      {errors.length > 0 && <div className="notice notice-danger">{errors.map((m) => <div key={m}>{m}</div>)}</div>}

      <form className="stack-lg" onSubmit={submit}>
        <Panel title="New Password">
          <Field label="New Password" required>
            <div className="row-tight">
              <input type={show ? 'text' : 'password'} className="input" value={v.new_password}
                onChange={(e) => setV({ ...v, new_password: e.target.value })} />
              <button type="button" className="btn btn-secondary btn-icon" onClick={() => setShow((s) => !s)} aria-label="Toggle password visibility">
                {show ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <PasswordMeter password={v.new_password} variant="change" />
          </Field>
          <Field label="Confirm New Password" required
            error={v.confirm_password && !matches ? 'Passwords do not match' : undefined}>
            <input type="password" className={`input ${v.confirm_password && !matches ? 'error' : ''}`} value={v.confirm_password}
              onChange={(e) => setV({ ...v, confirm_password: e.target.value })} />
          </Field>
          <div className="well" style={{ marginTop: 16 }}>
            <div className="section-title small">Password Requirements</div>
            <ul className="users-reqs">
              {REQUIREMENTS.map((r, i) => (
                <li key={r.key} className={met[i] ? 'is-met' : ''}>{met[i] ? <Check size={13} /> : <X size={13} />} <span>{r.label}</span></li>
              ))}
            </ul>
          </div>
        </Panel>

        <Panel title="Notification Settings">
          <div className="stack">
            <label className="check">
              <input type="checkbox" checked={v.send_email} onChange={(e) => setV({ ...v, send_email: e.target.checked })} />
              <span><strong>Send email notification to user</strong>
                <span className="field-help">An email will be sent to {t.email} with the new password and instructions.</span></span>
            </label>
            <label className="check">
              <input type="checkbox" checked={v.force_change} onChange={(e) => setV({ ...v, force_change: e.target.checked })} />
              <span><strong>Force password change on next login</strong>
                <span className="field-help">User will be required to change this password when they next login.</span></span>
            </label>
          </div>
        </Panel>

        <div className="row">
          <button className="btn btn-primary" type="submit" disabled={busy || !(allMet && matches)}>
            <Save size={14} /> {busy ? 'Updating Password...' : 'Update Password'}
          </button>
          <Link className="btn btn-secondary" to="/library/manage-users/"><X size={14} /> Cancel</Link>
        </div>
      </form>
    </div>
  );
}
