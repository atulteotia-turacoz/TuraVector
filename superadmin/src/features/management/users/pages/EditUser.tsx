import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Eye, Save, X } from 'lucide-react';
import { api } from '@/lib/api';
import { ErrorNotice, Field, Loading, PageHeader, Panel } from '@/components/ui';
import { formatDate, formatDateTime } from '@/lib/format';
import { useErrorToast, useFlash, usePageData, type ActionResult, type UserRow, type UserTypeItem } from '../shared';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function EditUser() {
  const { userId } = useParams();
  const q = usePageData<{ edited_user: UserRow; user_types: UserTypeItem[] }>(['edit', userId], `/api/users/${userId}/edit`);
  const navigate = useNavigate();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();
  const [v, setV] = useState<null | {
    first_name: string; last_name: string; email: string; username: string; phone: string; address: string;
    user_type: string; is_manager: boolean; is_active: boolean;
  }>(null);
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!q.data) return;
    const u = q.data.edited_user;
    // the <select required> shows the user's dynamic type, or the first active type when none is set
    const ut = q.data.user_types.find((t) => t.id === u.user_type_new_id) ?? q.data.user_types[0];
    setV({ first_name: u.first_name, last_name: u.last_name, email: u.email, username: u.username, phone: u.phone || '',
      address: u.address || '', user_type: ut ? String(ut.id) : '', is_manager: u.is_manager, is_active: u.is_active });
  }, [q.data]);

  if (q.isLoading || (q.data && !v)) return <Loading />;
  if (q.error || !q.data || !v) return <ErrorNotice error={q.error} />;
  const u = q.data.edited_user;
  const fullName = `${u.first_name} ${u.last_name}`.trim();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!v.first_name.trim() || !v.last_name.trim() || !v.email.trim() || !v.username.trim()) {
      setFormError('Please fill in all required fields.');
      return;
    }
    if (!EMAIL_RE.test(v.email.trim())) {
      setFormError('Please enter a valid email address.');
      return;
    }
    setFormError('');
    setBusy(true);
    try {
      const { data } = await api.post<ActionResult>(`/api/users/${u.id}/edit`, v);
      flash(data.messages, data.message);
      qc.invalidateQueries({ queryKey: ['users'] });
      navigate('/library/manage-users/');
    } catch (err) { showError(err); } finally { setBusy(false); }
  };
  const set = (k: keyof typeof v, val: string | boolean) => setV({ ...v, [k]: val });
  const req = (s: string) => (s.trim() === '' ? 'error' : '');

  return (
    <div className="stack-lg">
      <PageHeader title={`Edit User: ${fullName}`} subtitle="Modify user information and settings"
        actions={<>
          <Link className="btn btn-secondary" to="/library/manage-users/"><ArrowLeft size={14} /> Back to All Users</Link>
          <Link className="btn btn-secondary" to={`/library/user/${u.id}/view/`}><Eye size={14} /> View Profile</Link>
        </>} />
      {formError && <div className="notice notice-danger">{formError}</div>}
      <form className="detail-grid" onSubmit={submit} noValidate>
        <Panel title="Personal Information">
          <div className="form-grid">
            <Field label="First Name *"><input className={`input ${req(v.first_name)}`} value={v.first_name} onChange={(e) => set('first_name', e.target.value)} /></Field>
            <Field label="Last Name *"><input className={`input ${req(v.last_name)}`} value={v.last_name} onChange={(e) => set('last_name', e.target.value)} /></Field>
            <Field label="Email *"><input type="email" className={`input ${req(v.email)}`} value={v.email} onChange={(e) => set('email', e.target.value)} /></Field>
            <Field label="Username *"><input className={`input ${req(v.username)}`} value={v.username} onChange={(e) => set('username', e.target.value)} /></Field>
            <Field label="Phone"><input className="input" placeholder="Enter phone number" value={v.phone} onChange={(e) => set('phone', e.target.value)} /></Field>
            <Field label="User Type *">
              <select className="input" value={v.user_type} onChange={(e) => set('user_type', e.target.value)}>
                {q.data.user_types.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_system ? ' (System)' : ''}</option>)}
              </select>
            </Field>
            <div className="span-2">
              <Field label="Address"><textarea className="input" rows={3} placeholder="Enter full address" value={v.address} onChange={(e) => set('address', e.target.value)} /></Field>
            </div>
          </div>
        </Panel>

        <div className="stack-lg">
          <Panel title="Account Settings">
            <div className="stack">
              <label className="check">
                <input type="checkbox" checked={v.is_manager} onChange={(e) => set('is_manager', e.target.checked)} />
                <span><strong>Manager Privileges</strong><span className="field-help">Allow this user to manage other users and access admin features</span></span>
              </label>
              <label className="check">
                <input type="checkbox" checked={v.is_active} onChange={(e) => set('is_active', e.target.checked)} />
                <span><strong>Active Account</strong><span className="field-help">Allow this user to login and access the system</span></span>
              </label>
            </div>
          </Panel>
          <Panel title="Current Status">
            <dl className="kv">
              <dt>Joined</dt><dd>{formatDate(u.date_joined)}</dd>
              <dt>Last Login</dt><dd>{u.last_login ? formatDateTime(u.last_login) : 'Never'}</dd>
              <dt>Documents</dt><dd>{u.document_count ?? 0} total</dd>
            </dl>
          </Panel>
          <div className="stack">
            <button className="btn btn-primary btn-block" type="submit" disabled={busy}><Save size={14} /> Save Changes</button>
            <Link className="btn btn-secondary btn-block" to="/library/manage-users/"><X size={14} /> Cancel</Link>
          </div>
        </div>
      </form>
    </div>
  );
}
