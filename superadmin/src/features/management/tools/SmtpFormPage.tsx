import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Eye, EyeOff, Save, Send, X } from 'lucide-react';
import type { AxiosError } from 'axios';
import { api, errorMessage, toFormData } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { ErrorNotice, Field, Loading, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import type { SmtpConfig } from './api';
import './tools.css';

const PROVIDERS: Record<string, { label: string; host: string; port: number; use_tls: boolean; use_ssl: boolean }> = {
  gmail: { label: 'Gmail', host: 'smtp.gmail.com', port: 587, use_tls: true, use_ssl: false },
  outlook: { label: 'Outlook/Hotmail', host: 'smtp-mail.outlook.com', port: 587, use_tls: true, use_ssl: false },
  yahoo: { label: 'Yahoo Mail', host: 'smtp.mail.yahoo.com', port: 587, use_tls: true, use_ssl: false },
  sendgrid: { label: 'SendGrid', host: 'smtp.sendgrid.net', port: 587, use_tls: true, use_ssl: false },
};

interface FormState {
  host: string; port: string; use_tls: boolean; use_ssl: boolean; username: string; password: string;
  from_email: string; from_name: string; display_name: string; protocol: string; mailtype: string; charset: string;
  encoding: string; crlf: string; newline: string; status: string; wordwrap: boolean; test_email: string; is_active: boolean;
}

const DEFAULTS: FormState = {
  host: '', port: '587', use_tls: true, use_ssl: false, username: '', password: '',
  from_email: 'noreply@turadome.com', from_name: 'TuraVector Document System', display_name: 'TuraVector Document System',
  protocol: 'smtp', mailtype: 'html', charset: 'utf-8', encoding: '8bit', crlf: '\\r\\n', newline: '\\r\\n',
  status: 'active', wordwrap: true, test_email: '', is_active: true,
};

/** documents/smtp_settings_form.html (add + edit) */
export default function SmtpFormPage() {
  const { smtpId } = useParams();
  const editing = !!smtpId;
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [f, setF] = useState<FormState>(DEFAULTS);
  const [preset, setPreset] = useState<string | null>(null);
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);

  const q = useQuery({
    queryKey: ['tools', 'smtp', smtpId],
    enabled: editing,
    queryFn: async () => (await api.get<{ smtp_config: SmtpConfig }>(`/api/tools/smtp-settings/${smtpId}`)).data.smtp_config,
  });
  useEffect(() => {
    const c = q.data;
    if (!c) return;
    setF({
      host: c.host, port: String(c.port), use_tls: c.use_tls, use_ssl: c.use_ssl, username: c.username, password: c.password || '',
      from_email: c.from_email, from_name: c.from_name, display_name: c.display_name, protocol: c.protocol, mailtype: c.mailtype,
      charset: c.charset, encoding: c.encoding, crlf: c.crlf, newline: c.newline, status: c.status, wordwrap: c.wordwrap,
      test_email: c.test_email || '', is_active: c.is_active,
    });
  }, [q.data]);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((s) => ({ ...s, [k]: v }));

  const pick = (key: string) => {
    const p = PROVIDERS[key];
    setPreset(key);
    setF((s) => ({ ...s, host: p.host, port: String(p.port), use_tls: p.use_tls, use_ssl: p.use_ssl }));
  };
  // TLS and SSL are mutually exclusive; switch the conventional port with them
  const setTls = (on: boolean) => setF((s) => ({ ...s, use_tls: on, ...(on ? { use_ssl: false, port: s.port === '465' ? '587' : s.port } : {}) }));
  const setSsl = (on: boolean) => setF((s) => ({ ...s, use_ssl: on, ...(on ? { use_tls: false, port: s.port === '587' ? '465' : s.port } : {}) }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!f.host || !f.port || !f.username) { toast.error('Please fill in all required fields (Host, Port, Username)'); return; }
    const portNum = parseInt(f.port, 10);
    if (portNum < 1 || portNum > 65535) { toast.error('Port must be between 1 and 65535'); return; }
    if (!f.from_email || !f.from_name || (!editing && !f.password)) { toast.error('Please fill in all required fields'); return; }
    setBusy(true);
    try {
      const body = toFormData({
        action: editing ? 'update' : 'create',
        ...(editing ? { smtp_id: smtpId } : {}),
        host: f.host, port: f.port, username: f.username, password: f.password,
        use_tls: f.use_tls ? 'on' : undefined, use_ssl: f.use_ssl ? 'on' : undefined,
        from_email: f.from_email, from_name: f.from_name, display_name: f.display_name, protocol: f.protocol,
        mailtype: f.mailtype, charset: f.charset, encoding: f.encoding, crlf: f.crlf, newline: f.newline, status: f.status,
        wordwrap: f.wordwrap ? 'on' : undefined, test_email: f.test_email, is_active: f.is_active ? 'on' : undefined,
      });
      const { data } = await api.post(editing ? `/api/tools/smtp-settings/${smtpId}` : '/api/tools/smtp-settings', body);
      toast.success(data.message);
      qc.invalidateQueries({ queryKey: ['tools', 'smtp'] });
      navigate('/documents/smtp-settings/');
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  };

  const testConfig = async () => {
    setTesting(true);
    try {
      const { data } = await api.post(`/api/tools/smtp-settings/${smtpId}/test`);
      if (data.success) toast.success(`SMTP test successful: ${data.message}`);
      else toast.error(`SMTP test failed: ${data.message}`);
      setTimeout(() => q.refetch(), 2000);
    } catch (err) {
      const d = (err as AxiosError<any>).response?.data;
      toast.error(d?.error ? `SMTP test failed: ${d.error}` : 'Failed to test SMTP configuration');
    } finally { setTesting(false); }
  };

  if (editing && q.isLoading) return <Loading />;
  if (editing && q.error) return <ErrorNotice error={q.error} />;
  const cfg = q.data;

  return (
    <div className="tools-narrow stack-lg" style={{ maxWidth: 900 }}>
      <Link className="btn btn-ghost" to="/documents/smtp-settings/"><ArrowLeft size={14} /> Back to SMTP Settings</Link>
      <PageHeader title={`${editing ? 'Edit' : 'Add'} SMTP Configuration`} />
      <form onSubmit={submit} className="stack-lg">
        <Panel title="Server Configuration">
          {!editing && (
            <div style={{ marginBottom: 18 }}>
              <h3 className="section-title" style={{ marginTop: 0 }}>Quick Setup - Choose Provider</h3>
              <div className="tools-presets">
                {Object.entries(PROVIDERS).map(([k, p]) => (
                  <button type="button" key={k} className={`tools-preset ${preset === k ? 'is-selected' : ''}`} onClick={() => pick(k)}>
                    <strong>{p.label}</strong><div className="small muted">{p.host}:{p.port} (TLS)</div>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="form-grid">
            <Field label="SMTP Host" required help="The hostname of your SMTP server (e.g., smtp.gmail.com)">
              <input className="input" required placeholder="smtp.gmail.com" value={f.host} onChange={(e) => set('host', e.target.value)} />
            </Field>
            <Field label="Port" required help="Common: 587 (TLS), 465 (SSL), 25 (Plain)">
              <input className="input" type="number" min={1} max={65535} required value={f.port} onChange={(e) => set('port', e.target.value)} />
            </Field>
            <label className="check"><input type="checkbox" checked={f.use_tls} onChange={(e) => setTls(e.target.checked)} />
              <span><strong>Use TLS</strong><br /><span className="small muted">Recommended for port 587</span></span></label>
            <label className="check"><input type="checkbox" checked={f.use_ssl} onChange={(e) => setSsl(e.target.checked)} />
              <span><strong>Use SSL</strong><br /><span className="small muted">Usually for port 465</span></span></label>
            <div className="notice notice-accent span-2 small">
              <strong>Security Note:</strong> TLS is recommended for most providers. SSL is typically used with port 465.
            </div>
          </div>
        </Panel>

        <Panel title="Authentication">
          <div className="form-grid">
            <Field label="Username/Email" required help="Your email address or SMTP username">
              <input className="input" type="email" required placeholder="your-email@gmail.com" value={f.username}
                onChange={(e) => set('username', e.target.value)}
                onBlur={(e) => {
                  const email = e.target.value;
                  if ((!f.from_email || f.from_email === 'noreply@turadome.com') && email.includes('@')) set('from_email', email);
                }} />
            </Field>
            <Field label="Password" required={!editing} help={editing ? 'Leave blank to keep current password' : 'Your email password or app password'}>
              <div className="tools-pw">
                <input className="input" type={showPw ? 'text' : 'password'} required={!editing} placeholder="password"
                  value={f.password} onChange={(e) => set('password', e.target.value)} />
                <button type="button" className="btn btn-ghost btn-icon" aria-label="Toggle password" onClick={() => setShowPw((s) => !s)}>
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </Field>
          </div>
          <div className="notice notice-warn small" style={{ marginTop: 14 }}>
            <strong>Security Tip:</strong> For Gmail and other providers with 2-factor authentication, use an <strong>App Password</strong> instead
            of your regular password.{' '}
            <a className="act act-accent" href="https://support.google.com/accounts/answer/185833" target="_blank" rel="noreferrer">Learn how to create App Passwords</a>
          </div>
        </Panel>

        <Panel title="Email Settings">
          <div className="form-grid">
            <Field label="From Email" required help="The email address that will appear as sender">
              <input className="input" type="email" required value={f.from_email} placeholder="noreply@turadome.com" onChange={(e) => set('from_email', e.target.value)} />
            </Field>
            <Field label="From Name" required help="The display name for the sender">
              <input className="input" required value={f.from_name} placeholder="TuraVector Document System" onChange={(e) => set('from_name', e.target.value)} />
            </Field>
            <Field label="Display Name" help="Alternative display name for the sender">
              <input className="input" value={f.display_name} placeholder="TuraVector Document System" onChange={(e) => set('display_name', e.target.value)} />
            </Field>
            <Field label="Mail Protocol" help="Protocol to use for sending emails">
              <select className="input" value={f.protocol} onChange={(e) => set('protocol', e.target.value)}>
                <option value="smtp">SMTP</option><option value="mail">PHP Mail</option><option value="sendmail">Sendmail</option>
              </select>
            </Field>
            <Field label="Email Format" help="Format for email content">
              <select className="input" value={f.mailtype} onChange={(e) => set('mailtype', e.target.value)}>
                <option value="html">HTML</option><option value="text">Plain Text</option>
              </select>
            </Field>
            <Field label="Character Set" help="Character encoding for emails">
              <input className="input" value={f.charset} placeholder="utf-8" onChange={(e) => set('charset', e.target.value)} />
            </Field>
            <Field label="Encoding Method" help="Email encoding method">
              <select className="input" value={f.encoding} onChange={(e) => set('encoding', e.target.value)}>
                <option value="8bit">8bit</option><option value="7bit">7bit</option><option value="binary">Binary</option>
                <option value="base64">Base64</option><option value="quoted-printable">Quoted-Printable</option>
              </select>
            </Field>
          </div>
        </Panel>

        <Panel title="Advanced Settings">
          <div className="form-grid">
            <Field label="Line Ending (CRLF)" help="Line ending characters for emails">
              <input className="input mono" value={f.crlf} placeholder="\r\n" onChange={(e) => set('crlf', e.target.value)} />
            </Field>
            <Field label="Newline Character" help="Newline character for emails">
              <input className="input mono" value={f.newline} placeholder="\r\n" onChange={(e) => set('newline', e.target.value)} />
            </Field>
            <Field label="Status" help="Current configuration status">
              <select className="input" value={f.status} onChange={(e) => set('status', e.target.value)}>
                <option value="active">Active</option><option value="inactive">Inactive</option>
                <option value="testing">Testing</option><option value="error">Error</option>
              </select>
            </Field>
            <label className="check" style={{ alignSelf: 'end' }}><input type="checkbox" checked={f.wordwrap} onChange={(e) => set('wordwrap', e.target.checked)} />
              <span><strong>Enable Word Wrapping</strong><br /><span className="small muted">Automatically wrap long lines in emails</span></span></label>
          </div>
        </Panel>

        <Panel title="Testing & Status">
          <div className="form-grid">
            <Field label="Test Email (Optional)" help="Email address to send test messages to">
              <input className="input" type="email" placeholder="test@example.com" value={f.test_email} onChange={(e) => set('test_email', e.target.value)} />
            </Field>
            <label className="check" style={{ alignSelf: 'center' }}><input type="checkbox" checked={f.is_active} onChange={(e) => set('is_active', e.target.checked)} />
              <span><strong>Set as Active Configuration</strong><br /><span className="small muted">This will be used for sending emails</span></span></label>
          </div>
          {cfg && cfg.test_result && (
            <div className="well" style={{ marginTop: 16 }}>
              <div className="notice-title">Last Test Result</div>
              <div className="grid-2 small">
                <div>
                  <div><strong>Status:</strong> {cfg.is_tested ? <span className="badge badge-ok">Successful</span> : <span className="badge badge-danger">Failed</span>}</div>
                  <div><strong>Tested:</strong> {formatDateTime(cfg.last_tested)}</div>
                </div>
                <div><strong>Result:</strong><br /><span className="muted">{cfg.test_result}</span></div>
              </div>
            </div>
          )}
        </Panel>

        <div className="panel panel-body between">
          <Link className="btn btn-secondary" to="/documents/smtp-settings/"><X size={14} /> Cancel</Link>
          <div className="row">
            {editing && (
              <button type="button" className="btn btn-secondary" disabled={testing} onClick={testConfig}>
                {testing ? <><Spinner /> Testing...</> : <><Send size={14} /> Test Configuration</>}
              </button>
            )}
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? <Spinner /> : <Save size={14} />} {editing ? 'Update' : 'Create'} Configuration
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
