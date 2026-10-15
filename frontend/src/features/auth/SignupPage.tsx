/** Sign-up: an individual account (personal workspace), a university/organisation workspace
 * (approved by a superadmin), or a request to join an existing workspace with its join code. */
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Building2, CheckCircle2, KeyRound, LogIn, ShieldCheck, User, UserPlus } from 'lucide-react';
import { api, setToken } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { ThemePicker } from '@/components/ThemePicker';
import { Field, Spinner, Tabs, useToast } from '@/components/ui';
import { apiError, useTimezoneAutoDetect } from './utils';
import './auth.css';

interface SignupContext {
  user_types: { id: number; code: string; name: string }[];
  default_user_types: { value: string; label: string }[];
  organisation_kinds: { value: string; label: string }[];
}

type Mode = 'individual' | 'organisation' | 'join';
const MODES: Mode[] = ['individual', 'organisation', 'join'];

const INTRO: Record<Mode, string> = {
  individual: 'A personal workspace just for you. Your documents stay private to your account.',
  organisation: 'Create a workspace for your university or organisation. You become its administrator and can add students and researchers once we approve it.',
  join: 'Your university or organisation already uses TuraVector? Enter the join code they gave you. Their administrator approves your request.',
};

export default function SignupPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { refresh } = useAuth();
  const toast = useToast();
  useTimezoneAutoDetect();
  const ctx = useQuery({
    queryKey: ['auth', 'signup-context'],
    queryFn: async () => (await api.get('/api/auth/signup-context')).data as SignupContext,
  });
  const initial = params.get('type') as Mode | null;
  const [mode, setMode] = useState<Mode>(initial && MODES.includes(initial) ? initial : 'individual');
  const [form, setForm] = useState({
    first_name: '', last_name: '', username: '', email: '', phone: '', user_type: '', password: '', confirm_password: '', address: '',
    organisation_name: '', organisation_kind: 'university', website: '', join_code: params.get('code') ?? '',
  });
  const [logo, setLogo] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const userTypes = ctx.data?.default_user_types ?? [{ value: 'student', label: 'Student' }];
  const userType = form.user_type || userTypes[0].value;
  const mismatch = !!form.password && !!form.confirm_password && form.password !== form.confirm_password;
  const isOrg = mode === 'organisation';
  const orgLabel = form.organisation_kind === 'organisation' ? 'Organisation' : 'University';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!consent) { window.alert('You must consent to the processing of your personal data to create an account.'); return; }
    if (form.password !== form.confirm_password) { window.alert('Passwords do not match. Please check your passwords and try again.'); return; }
    if (form.password.length < 8) { window.alert('Password must be at least 8 characters long.'); return; }
    setBusy(true);
    setError(null);
    const account = {
      first_name: form.first_name, last_name: form.last_name, username: form.username, email: form.email,
      phone: form.phone, address: form.address, password: form.password, confirm_password: form.confirm_password,
    };
    try {
      if (isOrg) {
        const fd = new FormData();
        Object.entries({ ...account, organisation_name: form.organisation_name, organisation_kind: form.organisation_kind,
          website: form.website, privacy_consent: 'true' }).forEach(([k, v]) => fd.append(k, v));
        if (logo) fd.append('logo', logo);
        const { data } = await api.post('/api/auth/signup-organisation', fd);
        setDone(data.message);
      } else {
        const { data } = await api.post('/api/auth/signup', {
          ...account, user_type: userType, privacy_consent: consent, account_type: mode, join_code: form.join_code,
        });
        if (data.pending) {
          setDone(data.message);
        } else {
          setToken(data.access_token);
          await refresh();
          toast.success(data.message);
          navigate('/home', { replace: true });
          return;
        }
      }
      setBusy(false);
    } catch (err) {
      setError(apiError(err) || 'Network error occurred. Please check your connection and try again.');
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="au-floating-theme"><ThemePicker /></div>
      <div className="au-card is-wide">
        <div className="au-card-head">
          <Link to="/" className="logo">Join Tura<span className="logo-mark">Vector</span></Link>
          <p>Create your account to get started</p>
        </div>
        {done ? (
          <div className="au-card-body au-done">
            <CheckCircle2 size={34} className="au-done-icon" />
            <h2>{isOrg ? 'Registration received' : 'Request sent'}</h2>
            <p>{done}</p>
            <Link to="/login/" className="btn btn-primary"><LogIn size={15} /> Go to sign in</Link>
          </div>
        ) : (
          <div className="au-card-body">
            <div className="au-signup-tabs">
              <Tabs<Mode> value={mode} onChange={(m) => { setMode(m); setError(null); }} tabs={[
                { value: 'individual', label: <span className="row-tight"><User size={14} /> Individual</span> },
                { value: 'organisation', label: <span className="row-tight"><Building2 size={14} /> University / Organisation</span> },
                { value: 'join', label: <span className="row-tight"><KeyRound size={14} /> Join with code</span> },
              ]} />
            </div>
            <p className="au-signup-intro">{INTRO[mode]}</p>
            <form onSubmit={submit} id="signupForm">
              {error && <div className="notice notice-danger" style={{ marginBottom: 14 }}>{error}</div>}
              <div className="form-grid">
                {isOrg && <>
                  <div className="span-2 au-section-label">Your {orgLabel.toLowerCase()}</div>
                  <Field label="Type" required>
                    <select className="input" value={form.organisation_kind} onChange={set('organisation_kind')}>
                      {(ctx.data?.organisation_kinds ?? [{ value: 'university', label: 'University' }, { value: 'organisation', label: 'Organisation' }])
                        .map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                    </select>
                  </Field>
                  <Field label={`${orgLabel} Name`} required><input className="input" required value={form.organisation_name} onChange={set('organisation_name')} placeholder={`e.g. SMBT ${orgLabel}`} /></Field>
                  <Field label="Website"><input className="input" type="url" value={form.website} onChange={set('website')} placeholder="https://" /></Field>
                  <Field label="Logo" help="PNG or JPG, up to 2 MB. Shown in your workspace.">
                    <input className="input" type="file" accept="image/png,image/jpeg" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
                  </Field>
                  <div className="span-2 au-section-label">Administrator account</div>
                </>}
                {mode === 'join' && (
                  <div className="span-2">
                    <Field label="Join Code" required help="Ask your university or organisation administrator for this code.">
                      <input className="input au-code-input" required value={form.join_code} onChange={set('join_code')} placeholder="e.g. ARLLMN7E" autoComplete="off" />
                    </Field>
                  </div>
                )}
                <Field label="First Name" required><input className="input" required value={form.first_name} onChange={set('first_name')} placeholder="First Name" /></Field>
                <Field label="Last Name" required><input className="input" required value={form.last_name} onChange={set('last_name')} placeholder="Last Name" /></Field>
                <div className="span-2"><Field label="Username" required><input className="input" required value={form.username} onChange={set('username')} placeholder="Username" autoComplete="username" /></Field></div>
                <div className="span-2"><Field label="Email Address" required><input className="input" type="email" required value={form.email} onChange={set('email')} placeholder="Email Address" autoComplete="email" /></Field></div>
                <div className="span-2"><Field label="Phone Number"><input className="input" type="tel" value={form.phone} onChange={set('phone')} placeholder="Phone Number" /></Field></div>
                {!isOrg && (
                  <div className="span-2">
                    <Field label="I am a" required>
                      <select className="input" required value={userType} onChange={set('user_type')}>
                        {userTypes.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                      </select>
                    </Field>
                  </div>
                )}
                <Field label="Password" required><input className="input" type="password" required minLength={8} value={form.password} onChange={set('password')} autoComplete="new-password" /></Field>
                <Field label="Confirm Password" required error={mismatch ? 'Passwords do not match' : undefined}>
                  <input className="input" type="password" required minLength={8} value={form.confirm_password} onChange={set('confirm_password')} autoComplete="new-password" />
                </Field>
                <div className="span-2"><Field label="Address"><textarea className="input" rows={3} value={form.address} onChange={set('address')} placeholder="Address" /></Field></div>
              </div>
              <div className="au-consent">
                <label className="check" htmlFor="privacy_consent">
                  <input type="checkbox" id="privacy_consent" required checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                  <span>
                    <strong>I consent to the processing of my personal data in accordance with the{' '}
                      <a href="/documents/privacy-policy/" target="_blank" rel="noreferrer">Privacy Policy</a>.*</strong>
                    <small>By checking this box, you acknowledge that you have read and understood our Privacy Policy
                      and agree to the collection, processing, and storage of your personal information as described therein.</small>
                  </span>
                </label>
              </div>
              <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={!consent || busy} id="signupBtn">
                {busy ? <><Spinner /> {isOrg ? 'Registering...' : 'Creating Account...'}</>
                  : <><UserPlus size={16} /> {isOrg ? `Register ${orgLabel}` : mode === 'join' ? 'Request to Join' : 'Create Account'}</>}
              </button>
            </form>
          </div>
        )}
        <div className="au-card-foot">
          <div><Link to="/login/" className="row-tight" style={{ justifyContent: 'center' }}><LogIn size={13} /> Already have an account? Sign In</Link></div>
          <div className="row-tight" style={{ justifyContent: 'center' }}><ShieldCheck size={13} /> Your data is protected and secure</div>
        </div>
      </div>
    </div>
  );
}
