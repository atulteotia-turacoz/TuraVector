import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/lib/auth';
import { errorMessage } from '@/lib/api';
import { ThemePicker } from '@/components/ThemePicker';
import { NoAccess } from '@/components/Shell';

export default function Login() {
  const { user, login } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const next = params.get('next') || '/';

  if (user?.is_superuser) return <Navigate to={next} replace />;
  if (user && !user.is_superuser) return <NoAccess />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!consent) { setError('You must consent to the processing of your personal data in accordance with the Privacy Policy.'); return; }
    setBusy(true);
    try {
      const me = await login(username.trim(), password, consent);
      if (me.is_superuser) navigate(next.startsWith('/') ? next : '/', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'Login failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div style={{ position: 'fixed', top: 12, right: 16 }}><ThemePicker /></div>
      <div className="auth-card">
        <div style={{ marginBottom: 18 }}>
          <div className="logo" style={{ fontSize: 22 }}>Tura<span className="logo-mark">Vector</span> <span className="logo-sub">Admin</span></div>
          <p className="muted small" style={{ marginTop: 4 }}>Site administration — superusers only.</p>
        </div>
        <form className="panel" onSubmit={submit} noValidate>
          <div className="panel-body">
            {error && <div className="notice notice-danger" role="alert" style={{ marginBottom: 14 }}>{error}</div>}
            <label className="field">
              <span className="field-label">Username or email</span>
              <input className="input" autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
            </label>
            <label className="field">
              <span className="field-label">Password</span>
              <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            <label className="check" style={{ marginTop: 15 }}>
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>I consent to the processing of my personal data in accordance with the Privacy Policy.</span>
            </label>
          </div>
          <div className="panel-foot">
            <button className="btn btn-primary btn-block" disabled={busy || !username || !password}>{busy ? 'Logging in…' : 'Log in'}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
