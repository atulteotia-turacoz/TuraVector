import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Copy, Key } from 'lucide-react';
import { Badge, ErrorNotice, Loading, PageHeader, Panel } from '@/components/ui';
import { formatDateTime } from '@/lib/format';
import { usePageData, type UserRow } from '../shared';

interface ViewPasswordData {
  page_title: string;
  target_user: UserRow;
  password_info: { password: string; created_at: string; expires_at: string } | null;
  error_message: string | null;
}

export default function ViewPassword() {
  const { userId } = useParams();
  const q = usePageData<ViewPasswordData>(['view-password', userId], `/api/users/${userId}/view-password`, undefined, { gcTime: 0, staleTime: 0 });
  const [copied, setCopied] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorNotice error={q.error} />;
  const { target_user: t, password_info: info, error_message } = q.data;

  const copy = async () => {
    if (!info) return;
    try { await navigator.clipboard.writeText(info.password.trim()); } catch { /* ignore */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="page-narrow stack-lg" style={{ padding: 0 }}>
      <PageHeader title={q.data.page_title}
        actions={<Link className="btn btn-secondary" to="/library/manage-users/"><ArrowLeft size={14} /> Back to Manage Users</Link>} />
      <Panel title="Password Information">
        <div className="stack">
          <div className="section-title small">User Details</div>
          <dl className="kv">
            <dt>Name:</dt><dd>{`${t.first_name} ${t.last_name}`.trim()}</dd>
            <dt>Username:</dt><dd><code className="mono">{t.username}</code></dd>
            <dt>Email:</dt><dd>{t.email}</dd>
            <dt>User Type:</dt><dd><Badge>{t.user_type_display}</Badge></dd>
          </dl>
          <hr className="hairline" />
          {info ? (
            <>
              <div className="section-title small">Password</div>
              <div className="row users-password">
                <code className="mono grow">{info.password}</code>
                <button className="btn btn-secondary btn-sm" onClick={copy}><Copy size={14} /> {copied ? 'Copied!' : 'Copy'}</button>
              </div>
              <div className="notice notice-warn">
                <strong>Important:</strong>
                <ul>
                  <li>This password was stored on: {formatDateTime(info.created_at)}</li>
                  <li>It will expire on: <strong>{formatDateTime(info.expires_at)}</strong></li>
                  <li>After expiry, the password cannot be retrieved</li>
                  <li>For security, passwords are only stored temporarily</li>
                </ul>
              </div>
              <Link className="btn btn-primary" to={`/library/user/${t.id}/change-password/`}><Key size={14} /> Change Password</Link>
            </>
          ) : (
            <>
              <div className="notice notice-accent">
                <div className="notice-title">Password Not Available</div>
                <p>{error_message}</p>
              </div>
              <Link className="btn btn-primary" to={`/library/user/${t.id}/change-password/`}><Key size={14} /> Set New Password</Link>
            </>
          )}
        </div>
      </Panel>
      <div className="notice notice-danger">
        <div className="notice-title">Security Notice</div>
        This page displays sensitive information. Please ensure:
        <ul>
          <li>You are in a secure environment</li>
          <li>No one can see your screen</li>
          <li>You close this page after use</li>
          <li>You do not share or save passwords insecurely</li>
        </ul>
      </div>
    </div>
  );
}
