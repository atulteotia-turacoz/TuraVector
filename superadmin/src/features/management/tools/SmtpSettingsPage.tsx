import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Info, Pencil, Plus, Send, Server, Trash2 } from 'lucide-react';
import type { AxiosError } from 'axios';
import { api, errorMessage } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { Empty, ErrorNotice, Loading, Modal, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import type { SmtpConfig } from './api';
import './tools.css';

/** documents/smtp_settings.html */
export default function SmtpSettingsPage() {
  const toast = useToast();
  const [testing, setTesting] = useState<number | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const q = useQuery({
    queryKey: ['tools', 'smtp'],
    queryFn: async () => (await api.get<{ smtp_configurations: SmtpConfig[]; active_config: SmtpConfig | null }>('/api/tools/smtp-settings')).data,
  });

  const test = async (id: number) => {
    setTesting(id);
    try {
      const { data } = await api.post(`/api/tools/smtp-settings/${id}/test`);
      if (data.success) toast.success(`SMTP test successful: ${data.message}`);
      else toast.error(`SMTP test failed: ${data.message}`);
      setTimeout(() => q.refetch(), 2000);
    } catch (err) {
      const d = (err as AxiosError<any>).response?.data;
      toast.error(d?.error ? `SMTP test failed: ${d.error}` : 'Failed to test SMTP configuration');
    } finally { setTesting(null); }
  };

  const doDelete = async () => {
    if (deleteId === null) return;
    setDeleting(true);
    try {
      const { data } = await api.post(`/api/tools/smtp-settings/${deleteId}/delete`);
      toast.success(data.message);
      setDeleteId(null);
      q.refetch();
    } catch (err) { toast.error(errorMessage(err)); } finally { setDeleting(false); }
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const { smtp_configurations: configs, active_config: active } = q.data!;

  return (
    <div className="stack-lg">
      <PageHeader title="SMTP Settings" />
      <div className="grid-3" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)' }}>
        <Panel title="SMTP Configuration" actions={<Link className="btn btn-primary btn-sm" to="/documents/smtp-settings/add/"><Plus size={14} /> Add Configuration</Link>}>
          {configs.length === 0 ? (
            <Empty title="No SMTP Configurations" action={<Link className="btn btn-primary" to="/documents/smtp-settings/add/"><Plus size={14} /> Add SMTP Configuration</Link>}>
              Add your first SMTP configuration to start sending emails.
            </Empty>
          ) : configs.map((c) => (
            <div key={c.id} className={`tools-smtp-card ${c.is_active ? 'is-active' : ''}`}>
              <div className="between" style={{ alignItems: 'flex-start' }}>
                <div className="grow">
                  <div className="row wrap" style={{ marginBottom: 8 }}>
                    <strong>{c.host}:{c.port}</strong>
                    {c.is_active ? <span className="badge badge-ok">Active</span> : <span className="badge">Inactive</span>}
                    {c.is_tested && <span className="badge badge-accent">Tested</span>}
                  </div>
                  <div className="grid-2 small" style={{ gap: 4 }}>
                    <div><strong>Username:</strong> {c.username}</div>
                    <div><strong>Encryption:</strong> {c.use_tls ? 'TLS' : c.use_ssl ? 'SSL' : 'None'}</div>
                    <div><strong>From Email:</strong> {c.from_email}</div>
                    <div><strong>Created:</strong> {formatDateTime(c.created_at)}</div>
                    <div><strong>From Name:</strong> {c.from_name}</div>
                    {c.last_tested && <div><strong>Last Tested:</strong> {formatDateTime(c.last_tested)}</div>}
                  </div>
                  {c.test_result && (
                    <div className="small" style={{ marginTop: 8, color: c.is_tested ? 'var(--ok)' : 'var(--danger)' }}>
                      <strong>Test Result:</strong> {c.test_result}
                    </div>
                  )}
                </div>
                <div className="col" style={{ gap: 4 }}>
                  <Link className="btn btn-ghost btn-icon" title="Edit" to={`/documents/smtp-settings/edit/${c.id}/`}><Pencil size={14} /></Link>
                  <button className="btn btn-ghost btn-icon" title="Test" disabled={testing === c.id} onClick={() => test(c.id)}>
                    {testing === c.id ? <Spinner /> : <Send size={14} />}
                  </button>
                  {!c.is_active && (
                    <button className="btn btn-ghost btn-icon" title="Delete" onClick={() => setDeleteId(c.id)}><Trash2 size={14} /></button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </Panel>

        <div className="stack">
          <Panel title="SMTP Information">
            <div className="col">
              <div className="between"><span>Total Configurations</span><span className="badge badge-accent">{configs.length}</span></div>
              <div className="between"><span>Active Configuration</span>
                {active ? <span className="badge badge-ok">{active.host}</span> : <span className="badge badge-warn">None</span>}</div>
              <div className="between"><span>Tested Configurations</span><span className="badge">{configs.length}</span></div>
            </div>
          </Panel>
          <Panel title="Common SMTP Settings" flush>
            <table className="tbl">
              <thead><tr><th>Provider</th><th>Host</th><th>Port</th><th>TLS</th></tr></thead>
              <tbody>
                {[['Gmail', 'smtp.gmail.com'], ['Outlook', 'smtp-mail.outlook.com'], ['Yahoo', 'smtp.mail.yahoo.com'], ['SendGrid', 'smtp.sendgrid.net']].map(([p, h]) => (
                  <tr key={p}><td><strong>{p}</strong></td><td className="small">{h}</td><td>587</td><td>✓</td></tr>
                ))}
              </tbody>
            </table>
            <div className="panel-body small muted row-tight"><Info size={13} /> Use app passwords for Gmail and other providers that require 2FA.</div>
          </Panel>
        </div>
      </div>

      <Modal open={deleteId !== null} onClose={() => setDeleteId(null)} title="Delete SMTP Configuration"
        footer={<>
          <button className="btn btn-secondary" onClick={() => setDeleteId(null)}>Cancel</button>
          <button className="btn btn-danger" disabled={deleting} onClick={doDelete}>{deleting ? <Spinner /> : <Trash2 size={14} />} Delete</button>
        </>}>
        <div className="row-tight"><Server size={15} /> Are you sure you want to delete this SMTP configuration? This action cannot be undone.</div>
      </Modal>
    </div>
  );
}
