import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, X } from 'lucide-react';
import { api } from '@/lib/api';
import { ErrorNotice, Field, Loading, PageHeader, Panel } from '@/components/ui';
import { apiError, useFlash, usePageData, type ActionResult, type RoleItem, type UserTypeItem } from '../shared';
import { PasswordMeter } from '../components/PasswordMeter';

interface Workspace { id: number; name: string; kind: string }

const USERNAME_RE = /^[a-zA-Z0-9_]+$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function CreateUser() {
  const q = usePageData<{ user_types: UserTypeItem[]; roles: RoleItem[]; organisations: Workspace[] | null }>(['create-options'], '/api/users/create-options');
  const navigate = useNavigate();
  const flash = useFlash();
  const [v, setV] = useState({
    first_name: '', last_name: '', username: '', email: '', user_type: '', is_manager: false, role: '',
    phone: '', address: '', password: '', confirm_password: '', organisation: '',
  });
  const [usernameEdited, setUsernameEdited] = useState(false);
  const [invalid, setInvalid] = useState<Record<string, boolean>>({});
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { user_types, roles, organisations } = q.data;

  const set = (k: keyof typeof v, val: string | boolean) => {
    setV((cur) => {
      const next = { ...cur, [k]: val };
      // Auto-generate username from first and last name (until the username is edited by hand)
      if ((k === 'first_name' || k === 'last_name') && !usernameEdited) {
        const f = next.first_name.toLowerCase().replace(/[^a-z0-9]/g, '');
        const l = next.last_name.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (f && l) next.username = f.charAt(0) + l;
      }
      return next;
    });
    setInvalid((i) => ({ ...i, [k]: false }));
  };

  const description = user_types.find((t) => String(t.id) === v.user_type)?.description?.trim();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const bad: Record<string, boolean> = {};
    if (!v.first_name.trim()) bad.first_name = true;
    if (!v.last_name.trim()) bad.last_name = true;
    if (v.password !== v.confirm_password) bad.confirm_password = true;
    if (v.password.length < 8) bad.password = true;
    if (!USERNAME_RE.test(v.username)) bad.username = true;
    if (!EMAIL_RE.test(v.email)) bad.email = true;
    if (!v.user_type) bad.user_type = true;
    if (organisations && !v.organisation) bad.organisation = true;
    setInvalid(bad);
    if (Object.keys(bad).length) return;
    setBusy(true);
    setServerErrors([]);
    try {
      const { data } = await api.post<ActionResult>('/api/users/create', v);
      flash(data.messages, data.message);
      navigate('/library/manage-users/');
    } catch (err) {
      setServerErrors(apiError(err).messages);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setBusy(false);
    }
  };

  const liveInvalid = {
    username: v.username.length > 0 && !USERNAME_RE.test(v.username),
    email: v.email.length > 0 && !EMAIL_RE.test(v.email),
    password: v.password.length > 0 && v.password.length < 8,
    confirm_password: v.confirm_password.length > 0 && v.password !== v.confirm_password,
  };

  return (
    <div className="stack-lg">
      <PageHeader title="Create New User"
        actions={<Link className="btn btn-secondary" to="/library/manage-users/"><ArrowLeft size={14} /> Back to All Users</Link>} />

      {serverErrors.length > 0 && (
        <div className="notice notice-danger">{serverErrors.map((m) => <div key={m}>{m}</div>)}</div>
      )}

      <form className="stack-lg" onSubmit={submit} noValidate>
        <Panel title="Basic Information">
          <div className="form-grid">
            <Field label="First Name" required error={invalid.first_name && 'Please enter a first name.'}>
              <input className={`input ${invalid.first_name ? 'error' : ''}`} value={v.first_name} onChange={(e) => set('first_name', e.target.value)} />
            </Field>
            <Field label="Last Name" required error={invalid.last_name && 'Please enter a last name.'}>
              <input className={`input ${invalid.last_name ? 'error' : ''}`} value={v.last_name} onChange={(e) => set('last_name', e.target.value)} />
            </Field>
            <Field label="Username" required help="Must be unique and contain only letters, numbers, and underscores"
              error={(invalid.username || liveInvalid.username) && 'Username must contain only letters, numbers, and underscores.'}>
              <input className={`input ${invalid.username || liveInvalid.username ? 'error' : ''}`} value={v.username}
                onKeyDown={() => setUsernameEdited(true)} onChange={(e) => set('username', e.target.value)} />
            </Field>
            <Field label="Email Address" required error={(invalid.email || liveInvalid.email) && 'Please enter a valid email address.'}>
              <input type="email" className={`input ${invalid.email || liveInvalid.email ? 'error' : ''}`} value={v.email} onChange={(e) => set('email', e.target.value)} />
            </Field>
          </div>
        </Panel>

        <Panel title="User Type & Permissions">
          <div className="form-grid">
            {organisations && (
              <Field label="Workspace" required error={invalid.organisation && 'Please choose a workspace.'}
                help="The university or organisation this user belongs to. They only see that workspace's data.">
                <select className={`input ${invalid.organisation ? 'error' : ''}`} value={v.organisation} onChange={(e) => set('organisation', e.target.value)}>
                  <option value="">Select workspace...</option>
                  {organisations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
              </Field>
            )}
            <Field label="User Type" required error={invalid.user_type && 'Please select a user type.'}
              help={description || 'Select a user type to see its description'}>
              <select className={`input ${invalid.user_type ? 'error' : ''}`} value={v.user_type} onChange={(e) => set('user_type', e.target.value)}>
                <option value="">Select user type...</option>
                {user_types.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_system ? ' (System)' : ''}</option>)}
              </select>
            </Field>
            <div className="field">
              <span className="field-label">Manager Privileges</span>
              <label className="check">
                <input type="checkbox" checked={v.is_manager} onChange={(e) => set('is_manager', e.target.checked)} />
                <span>Grant manager privileges<span className="field-help">Allows access to management features</span></span>
              </label>
            </div>
            <Field label="Role (Optional)" help="Assign a predefined role with specific permissions">
              <select className="input" value={v.role} onChange={(e) => set('role', e.target.value)}>
                <option value="">No specific role</option>
                {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </Field>
          </div>
        </Panel>

        <Panel title="Contact Information">
          <div className="form-grid">
            <Field label="Phone Number">
              <input type="tel" className="input" placeholder="+1 (555) 123-4567" value={v.phone} onChange={(e) => set('phone', e.target.value)} />
            </Field>
            <Field label="Address">
              <textarea className="input" rows={2} placeholder="Enter address..." value={v.address} onChange={(e) => set('address', e.target.value)} />
            </Field>
          </div>
        </Panel>

        <Panel title="Security">
          <div className="form-grid">
            <Field label="Password" required help="Minimum 8 characters"
              error={(invalid.password || liveInvalid.password) && 'Password must be at least 8 characters long.'}>
              <input type="password" className={`input ${invalid.password || liveInvalid.password ? 'error' : ''}`} value={v.password}
                onChange={(e) => set('password', e.target.value)} />
              <PasswordMeter password={v.password} variant="create" />
            </Field>
            <Field label="Confirm Password" required error={(invalid.confirm_password || liveInvalid.confirm_password) && 'Passwords do not match.'}>
              <input type="password" className={`input ${invalid.confirm_password || liveInvalid.confirm_password ? 'error' : ''}`}
                value={v.confirm_password} onChange={(e) => set('confirm_password', e.target.value)} />
            </Field>
          </div>
          <div className="notice notice-accent" style={{ marginTop: 16 }}>
            <strong>Note:</strong> A welcome email will be sent to the user with their login credentials.
          </div>
        </Panel>

        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <Link className="btn btn-secondary" to="/library/manage-users/"><X size={14} /> Cancel</Link>
          <button className="btn btn-primary" type="submit" disabled={busy}><Save size={14} /> {busy ? 'Creating User...' : 'Create User'}</button>
        </div>
      </form>
    </div>
  );
}
