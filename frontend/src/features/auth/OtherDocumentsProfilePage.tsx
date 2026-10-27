/** Port of templates/documents/other_documents_profile.html (other_documents_profile_view). */
import { useEffect, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CircleUser, Crown, Globe, Info, KeyRound, Pencil, Save } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth, useUser } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { Badge, ErrorNotice, Field, Loading, PageHeader, Panel, Spinner, Stat, useToast } from '@/components/ui';
import { ChangePasswordModal, TimezoneSelector } from './components';
import { apiError, formatDateTime24, useTimezoneAutoDetect } from './utils';
import './auth.css';

interface OdProfile {
  total_documents: number;
  total_versions: number;
}

export default function OtherDocumentsProfilePage() {
  const user = useUser();
  const { refresh } = useAuth();
  const toast = useToast();
  useTimezoneAutoDetect();
  const q = useQuery({
    queryKey: ['auth', 'od-profile'],
    queryFn: async () => (await api.get('/api/documents/other-documents/profile')).data as OdProfile,
  });
  const [pwOpen, setPwOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', phone: '' });
  useEffect(() => {
    setForm({ first_name: user.first_name, last_name: user.last_name, email: user.email, phone: user.phone ?? '' });
  }, [user]);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post('/api/auth/update-profile', form);
      if (data.message) {
        toast.success('Profile updated successfully!');
        window.setTimeout(() => { void refresh(); void q.refetch(); }, 1500);
      } else {
        toast.error(data.error || 'Error updating profile');
      }
    } catch (err) {
      toast.error(apiError(err) || 'Error updating profile');
    } finally {
      setBusy(false);
    }
  };

  const getFullName = `${user.first_name} ${user.last_name}`.trim();
  const initials = `${(user.first_name || '').charAt(0)}${(user.last_name || '').charAt(0)}`.toUpperCase();
  const d = q.data;

  return (
    <div className="stack-lg">
      <PageHeader title="My Profile" />
      <div className="detail-grid">
        <div className="stack-lg">
          <section className="panel">
            <div className="au-profile-hero">
              <div className="au-avatar-lg">{initials}</div>
              <div>
                <h1>{getFullName || user.username}</h1>
                <div className="muted">{user.user_type_display || 'User'}</div>
              </div>
            </div>
            {q.isLoading && <Loading />}
            {q.isError && <div className="panel-body"><ErrorNotice error={q.error} /></div>}
            {d && (
              <div className="stat-grid" style={{ border: 0, borderBottom: '1px solid var(--hairline)' }}>
                <Stat value={d.total_documents} label="Total Documents" />
                <Stat value={d.total_versions} label="Document Versions" />
              </div>
            )}
          </section>

          <Panel title={<span className="row-tight"><CircleUser size={15} /> Personal Information</span>}>
            <dl className="kv" style={{ margin: 0 }}>
              <dt>Full Name</dt><dd>{getFullName || 'Not provided'}</dd>
              <dt>Email Address</dt><dd>{user.email}</dd>
              <dt>Username</dt><dd>{user.username}</dd>
              <dt>User Type</dt><dd>{user.user_type_display || 'Standard User'}</dd>
              {user.phone && <><dt>Phone</dt><dd>{user.phone}</dd></>}
              {user.timezone && <><dt>Timezone</dt><dd>{user.timezone}</dd></>}
            </dl>
          </Panel>

          <Panel title={<span className="row-tight"><Pencil size={15} /> Edit Information</span>}>
            <form onSubmit={submit} id="profileForm">
              <div className="form-grid">
                <Field label="First Name"><input className="input" required value={form.first_name} onChange={set('first_name')} /></Field>
                <Field label="Last Name"><input className="input" required value={form.last_name} onChange={set('last_name')} /></Field>
                <Field label="Email"><input className="input" type="email" required value={form.email} onChange={set('email')} /></Field>
                <Field label="Phone"><input className="input" value={form.phone} onChange={set('phone')} /></Field>
              </div>
              <div className="row" style={{ justifyContent: 'center', marginTop: 18 }}>
                <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : <Save size={14} />} Update Profile</button>
                <button type="button" className="btn btn-secondary" onClick={() => setPwOpen(true)}><KeyRound size={14} /> Change Password</button>
              </div>
            </form>
          </Panel>

          <Panel title={<span className="row-tight"><Globe size={15} /> Timezone Preferences</span>}>
            <div className="section-title" style={{ marginTop: 0 }}>Timezone Settings</div>
            <TimezoneSelector />
          </Panel>
        </div>

        <Panel title={<span className="row-tight"><Info size={15} /> Account Summary</span>}>
          <dl className="au-summary" style={{ margin: 0, gridTemplateColumns: '1fr' }}>
            <div><dt>User ID</dt><dd>{user.id}</dd></div>
            <div><dt>Account Status</dt><dd>{user.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Inactive</Badge>}</dd></div>
            <div><dt>Member Since</dt><dd>{formatDate(user.date_joined)}</dd></div>
            <div><dt>Last Login</dt><dd>{user.last_login ? formatDateTime24(user.last_login, user.timezone) : 'Never'}</dd></div>
            {user.is_manager && (
              <div><dt>Manager Privileges</dt><dd><Badge tone="accent"><Crown size={12} style={{ verticalAlign: '-2px' }} /> Manager</Badge></dd></div>
            )}
          </dl>
        </Panel>
      </div>
      <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)} variant="other" />
    </div>
  );
}
