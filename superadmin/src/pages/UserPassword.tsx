import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, errorMessage } from '@/lib/api';
import { API, formErrors } from '@/lib/admin';
import { ErrorNotice, Loading, PageHeader, Panel, useToast } from '@/components/ui';
import { Crumbs } from '@/components/Shell';

interface PwForm { pk: string; username: string; str: string; title: string; usable: boolean; help: string[] }

export default function UserPassword() {
  const { pk = '' } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'password', pk], queryFn: async () => (await api.get<PwForm>(`${API}/users/${pk}/password`)).data });
  const [usable, setUsable] = useState('true');
  const [p1, setP1] = useState('');
  const [p2, setP2] = useState('');
  const [errors, setErrors] = useState<Record<string, string[]> | null>(null);
  const [busy, setBusy] = useState(false);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const d = q.data!;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setErrors(null);
    try {
      const { data } = await api.post(`${API}/users/${pk}/password`, { usable_password: usable, password1: p1, password2: p2 });
      toast.success(data.message);
      void qc.invalidateQueries({ queryKey: ['admin'] });
      navigate(`/authentication/user/${pk}/change/`);
    } catch (err) {
      const fe = formErrors(err);
      if (fe?.errors) setErrors(fe.errors); else toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const errList = (k: string) => errors?.[k]?.length ? <ul className="errorlist" role="alert">{errors[k].map((x, i) => <li key={i}>{x}</li>)}</ul> : null;
  const n = errors ? Object.values(errors).reduce((a, b) => a + b.length, 0) : 0;

  return (
    <>
      <Crumbs items={[
        { label: 'Authentication', to: '/authentication/' },
        { label: 'Users', to: '/authentication/user/' },
        { label: d.str, to: `/authentication/user/${pk}/change/` },
        { label: 'Change password' },
      ]} />
      <PageHeader title={d.title} />
      {errors && <div className="notice notice-danger" role="alert" style={{ marginBottom: 14 }}>{n === 1 ? 'Please correct the error below.' : 'Please correct the errors below.'}</div>}
      <p className="muted" style={{ marginBottom: 14 }}>Enter a new password for the user <strong>{d.username}</strong>.</p>
      <form onSubmit={submit} noValidate>
        <Panel flush>
          <div className="form-row">
            <span className="form-label">Password-based authentication</span>
            <div>
              <div className="row wrap" style={{ paddingTop: 6 }}>
                <label className="check"><input type="radio" name="usable" checked={usable === 'true'} onChange={() => setUsable('true')} /> Enabled</label>
                <label className="check"><input type="radio" name="usable" checked={usable === 'false'} onChange={() => setUsable('false')} /> Disabled</label>
              </div>
              <span className="field-help">Whether the user will be able to authenticate using a password or not. If disabled, they may still be able to authenticate using other backends, such as Single Sign-On or LDAP.</span>
            </div>
          </div>
          {usable === 'true' && (
            <>
              <div className={`form-row ${errors?.password1 ? 'has-error' : ''}`}>
                <label className="form-label required" htmlFor="pw1">Password</label>
                <div>{errList('password1')}<input id="pw1" className="input" style={{ maxWidth: 360 }} type="password" autoComplete="new-password" value={p1} onChange={(e) => setP1(e.target.value)} />
                  <ul className="field-help" style={{ paddingLeft: 18 }}>{d.help.map((h) => <li key={h}>{h}</li>)}</ul></div>
              </div>
              <div className={`form-row ${errors?.password2 ? 'has-error' : ''}`}>
                <label className="form-label required" htmlFor="pw2">Password (again)</label>
                <div>{errList('password2')}<input id="pw2" className="input" style={{ maxWidth: 360 }} type="password" autoComplete="new-password" value={p2} onChange={(e) => setP2(e.target.value)} />
                  <span className="field-help">Enter the same password as before, for verification.</span></div>
              </div>
            </>
          )}
        </Panel>
        <div className="submit-row">
          <button className="btn btn-primary" disabled={busy}>{usable === 'true' ? 'Change password' : 'Disable password-based authentication'}</button>
          <Link className="btn btn-secondary" to={`/authentication/user/${pk}/change/`}>Cancel</Link>
        </div>
      </form>
    </>
  );
}
