/** Port of templates/authentication/profile.html (profile_view). */
import { useEffect, useState, type FormEvent } from 'react';
import { Crown, Globe, Info, KeyRound, Save, User } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth, useUser } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { Badge, Field, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import { ChangePasswordModal, TimezoneSelector } from './components';
import { apiError, useTimezoneAutoDetect } from './utils';
import './auth.css';

export default function ProfilePage() {
  const user = useUser();
  const { refresh } = useAuth();
  const toast = useToast();
  useTimezoneAutoDetect();
  const [pwOpen, setPwOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', phone: '', address: '' });
  useEffect(() => {
    setForm({ first_name: user.first_name, last_name: user.last_name, email: user.email, phone: user.phone ?? '', address: user.address ?? '' });
  }, [user]);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post('/api/auth/update-profile', form);
      toast.success('Profile updated successfully!');
      await refresh();
    } catch (err) {
      const msg = apiError(err);
      toast.error(msg ? `Error: ${msg}` : 'An error occurred while updating profile');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack-lg">
      <PageHeader title="User Profile" />
      <div className="detail-grid">
        <div className="stack-lg">
          <Panel title={<span className="row-tight"><User size={15} /> Profile Information</span>}>
            <form onSubmit={submit} id="profileForm">
              <div className="form-grid">
                <Field label="First Name"><input className="input" required value={form.first_name} onChange={set('first_name')} /></Field>
                <Field label="Last Name"><input className="input" required value={form.last_name} onChange={set('last_name')} /></Field>
                <Field label="Email"><input className="input" type="email" required value={form.email} onChange={set('email')} /></Field>
                <Field label="Username" help="Username cannot be changed"><input className="input" value={user.username} disabled /></Field>
                <Field label="Phone"><input className="input" value={form.phone} onChange={set('phone')} /></Field>
                <Field label="User Type"><input className="input" value={user.user_type_display} disabled /></Field>
                <div className="span-2"><Field label="Address"><textarea className="input" rows={3} value={form.address} onChange={set('address')} /></Field></div>
              </div>
              <div className="between" style={{ marginTop: 18 }}>
                <button type="button" className="btn btn-secondary" onClick={() => setPwOpen(true)}><KeyRound size={14} /> Change Password</button>
                <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : <Save size={14} />} Update Profile</button>
              </div>
            </form>
          </Panel>
          <Panel title={<span className="row-tight"><Globe size={15} /> Timezone Preferences</span>}>
            <div className="section-title" style={{ marginTop: 0 }}>Timezone Settings</div>
            <TimezoneSelector />
          </Panel>
        </div>
        <Panel title={<span className="row-tight"><Info size={15} /> Account Summary</span>}>
          <dl className="au-summary" style={{ margin: 0 }}>
            <div><dt>User ID</dt><dd>{user.id}</dd></div>
            <div><dt>Account Status</dt><dd>{user.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Inactive</Badge>}</dd></div>
            <div><dt>Member Since</dt><dd>{formatDate(user.date_joined)}</dd></div>
            <div><dt>Last Login</dt><dd>{user.last_login ? formatDate(user.last_login) : 'Never'}</dd></div>
            {user.is_manager && (
              <div className="span-2"><dt>Manager Privileges</dt><dd><Badge tone="accent"><Crown size={12} style={{ verticalAlign: '-2px' }} /> Manager</Badge></dd></div>
            )}
          </dl>
        </Panel>
      </div>
      <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)} variant="main" />
    </div>
  );
}
