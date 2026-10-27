/** Port of templates/authentication/login.html (+ forgot-password OTP modal). */
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { KeyRound, LogIn, ShieldCheck, UserPlus } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { ThemePicker } from '@/components/ThemePicker';
import { Field, Modal, Spinner, useToast } from '@/components/ui';
import { apiError, detectAndSetTimezone, safeNext, useTimezoneAutoDetect } from './utils';
import './auth.css';

const NETWORK_ERROR = 'Network error occurred. Please check your connection and try again.';

function ForgotPasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [showOtp, setShowOtp] = useState(false);
  const [sending, setSending] = useState(false);
  const [resetting, setResetting] = useState(false);

  const sendOtp = async (e: FormEvent) => {
    e.preventDefault();
    setSending(true);
    try {
      const { data } = await api.post('/api/auth/forgot-password', { email });
      toast.success(`Success: ${data.message}`);
      setShowOtp(true);
    } catch (err) {
      const msg = apiError(err);
      toast.error(msg ? `Error: ${msg}` : NETWORK_ERROR);
    } finally {
      setSending(false);
    }
  };

  const resetPassword = async (e: FormEvent) => {
    e.preventDefault();
    setResetting(true);
    try {
      const { data } = await api.post('/api/auth/verify-otp', { email, otp, new_password: newPassword });
      toast.success(`Success: ${data.message}`);
      onClose();
      setEmail(''); setOtp(''); setNewPassword(''); setShowOtp(false);
    } catch (err) {
      const msg = apiError(err);
      toast.error(msg ? `Error: ${msg}` : NETWORK_ERROR);
    } finally {
      setResetting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Reset Password">
      <form className="stack" onSubmit={sendOtp} id="forgotPasswordForm">
        <Field label="Email Address"><input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></Field>
        <button type="submit" className="btn btn-primary btn-block" disabled={sending}>{sending ? <><Spinner /> Sending...</> : 'Send OTP'}</button>
      </form>
      {showOtp && (
        <>
          <hr className="hairline" style={{ margin: '18px 0' }} />
          <form className="stack" onSubmit={resetPassword} id="otpForm">
            <Field label="Enter OTP"><input className="input" required value={otp} onChange={(e) => setOtp(e.target.value)} autoComplete="one-time-code" /></Field>
            <Field label="New Password"><input className="input" type="password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" /></Field>
            <button type="submit" className="btn btn-primary btn-block" disabled={resetting}>{resetting ? <><Spinner /> Resetting...</> : 'Reset Password'}</button>
          </form>
        </>
      )}
    </Modal>
  );
}

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  useTimezoneAutoDetect();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!consent) {
      window.alert('You must consent to the processing of your personal data to proceed with login.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(username, password, consent);
      detectAndSetTimezone();
      navigate(safeNext(params.get('next')) || '/home', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'Invalid username or password'));
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="au-floating-theme"><ThemePicker /></div>
      <div className="au-card">
        <div className="au-card-head">
          <Link to="/" className="logo">Tura<span className="logo-mark">Vector</span></Link>
          <p>Document Management System</p>
        </div>
        <form className="au-card-body" onSubmit={submit} id="loginForm">
          {error && <div className="notice notice-danger" style={{ marginBottom: 14 }}>{error}</div>}
          <div className="stack">
            <Field label="Username"><input className="input" name="username" required autoFocus value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder="Username" /></Field>
            <Field label="Password"><input className="input" name="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" placeholder="Password" /></Field>
          </div>
          <div className="au-consent">
            <label className="check" htmlFor="privacy_consent">
              <input type="checkbox" id="privacy_consent" name="privacy_consent" required checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>
                <strong>I consent to the processing of my personal data as described in the{' '}
                  <a href="/documents/privacy-policy/" target="_blank" rel="noreferrer">Privacy Policy</a>.*</strong>
                <small>By checking this box, I confirm that I have read and understood the Privacy Policy.</small>
              </span>
            </label>
          </div>
          <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={!consent || busy} id="loginBtn">
            {busy ? <Spinner /> : <LogIn size={16} />} Sign In
          </button>
        </form>
        <div className="au-card-foot">
          <div><button type="button" className="au-linkbtn" onClick={() => setForgotOpen(true)}><KeyRound size={13} style={{ verticalAlign: '-2px' }} /> Forgot Password?</button></div>
          <div><Link to="/signup/" className="row-tight" style={{ justifyContent: 'center' }}><UserPlus size={13} /> New to TuraVector? Create an account</Link></div>
          <div className="row-tight" style={{ justifyContent: 'center' }}><ShieldCheck size={13} /> Secure • Reliable • Efficient</div>
          <div className="row wrap" style={{ justifyContent: 'center' }}>
            <span className="faint">© 2024 TuraVector. All rights reserved.</span>
            <Link to="/documents/terms-and-conditions/">Terms</Link>
            <span className="faint">•</span>
            <Link to="/documents/privacy-policy/">Privacy</Link>
          </div>
        </div>
      </div>
      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
    </div>
  );
}
