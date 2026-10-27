/** Port of templates/documents/dashboard_selection.html (dashboard_selection_view). Standalone page. */
import { useEffect, useState, type MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Check, CreditCard, ExternalLink, FileText, FlaskConical, Lock, Sparkles } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { useUser } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Loading, useToast } from '@/components/ui';
import { ToolIcon, dueLabel, money, type Subscription, type Tool } from '@/features/plans/shared';
import { ThemePicker } from '@/components/ThemePicker';
import { NotificationBell, UserMenu } from '@/layouts/AppShell';
import { BareFrame } from './components';
import { useTimezoneAutoDetect } from './utils';
import './auth.css';
import '@/features/plans/plans.css';

interface Selection {
  can_access_content_lab: boolean;
  can_access_other_documents: boolean;
  dashboards: Partial<Record<'content_lab' | 'other_documents', Tool>>;
  apps: { key: string; name: string; description: string; features: string[]; url: string; sso: boolean; icon: string }[];
  can_manage_plans: boolean;
  subscriptions: Subscription[];
  pending: Subscription[];
  locked_tools: (Tool & { plan_count: number; from_price: number; currency: string; from_period: string })[];
  redirect: string | null;
  error: string | null;
}

const OPTIONS = [
  {
    key: 'content_lab' as const,
    to: '/content-lab-management/dashboard/',
    icon: <FlaskConical size={22} />,
    title: 'Content Review',
    description: 'Access all existing TuraVector features for comprehensive document management and collaboration.',
    features: ['Document Upload & Version Control', 'PDF Annotation & Review', 'Collaborative Editing',
      'Reference Library Management', 'User Management & Permissions', 'Email Notifications & Workflow'],
  },
  {
    key: 'other_documents' as const,
    to: '/journal-selector/dashboard/',
    icon: <FileText size={22} />,
    title: 'Journal Selector',
    description: 'Access specialized document management features for different document types and workflows.',
    features: ['Specialized Document Types', 'Custom Workflows', 'Advanced Processing', 'Extended Integrations',
      'Custom Templates', 'Enhanced Analytics'],
  },
];

export default function DashboardSelectionPage() {
  const user = useUser();
  const navigate = useNavigate();
  const toast = useToast();
  const [going, setGoing] = useState<string | null>(null);
  useTimezoneAutoDetect();
  const q = useQuery({
    queryKey: ['auth', 'dashboard-selection', user.id],
    queryFn: async () => (await api.get('/api/documents/dashboard-selection')).data as Selection,
    staleTime: 0,
  });

  useEffect(() => {
    if (!q.data?.redirect) return;
    if (q.data.error) toast.error(q.data.error);
    navigate(q.data.redirect, { replace: true });
  }, [q.data, navigate, toast]);

  const go = (e: MouseEvent, to: string) => {
    e.preventDefault();
    setGoing(to);
    window.setTimeout(() => navigate(to), 200);
  };

  // Single sign-on: the backend returns a URL that opens the app already signed in.
  // The tab is opened synchronously (inside the click) so pop-up blockers allow it.
  const launch = async (e: MouseEvent, key: string) => {
    e.preventDefault();
    const tab = window.open('about:blank', '_blank');
    setGoing(key);
    try {
      const { url } = (await api.post(`/api/documents/external-apps/${key}/launch`)).data as { url: string };
      if (tab) {
        tab.opener = null;
        tab.location.href = url;
      } else {
        window.location.href = url;
      }
    } catch (err) {
      tab?.close();
      toast.error(errorMessage(err, 'Could not open the application.'));
    } finally {
      setGoing(null);
    }
  };

  const dashboards = OPTIONS.filter((o) => (o.key === 'content_lab' ? q.data?.can_access_content_lab : q.data?.can_access_other_documents));

  // same theme / notifications / user menu as the dashboards' top bar
  const right = (
    <>
      <ThemePicker />
      <NotificationBell />
      <UserMenu profilePath="/profile/" />
    </>
  );

  return (
    <BareFrame right={right} theme={false}>
      {(q.isLoading || q.data?.redirect) && <Loading />}
      {q.isError && <div className="au-select"><ErrorNotice error={q.error} /></div>}
      {q.data && !q.data.redirect && (
        <div className="au-select">
          <div className="au-select-head">
            <h1>Welcome to {user.organisation && user.organisation.kind !== 'individual' ? user.organisation.name : 'TuraVector'}</h1>
            <p>Select your preferred dashboard to get started</p>
          </div>
          {q.data.pending.length > 0 && (
            <div className="notice notice-warn pl-banner">
              <span><strong>{q.data.pending[0].plan_name}</strong> is waiting for payment ({dueLabel(q.data.pending[0])}). Its tools unlock as soon as it's paid.</span>
              <Link className="btn btn-primary btn-sm" to={`/plans/?pay=${q.data.pending[0].id}`}><CreditCard size={14} /> Complete payment</Link>
            </div>
          )}
          {(q.data.subscriptions.length > 0 || q.data.can_manage_plans) && (
            <div className="notice pl-banner">
              <span className="row-tight wrap">
                <Sparkles size={15} />
                {q.data.subscriptions.length > 0
                  ? q.data.subscriptions.map((s) => (
                    <span key={s.id}><strong>{s.plan_name}</strong>{s.is_trial ? ' (trial)' : ''}{s.ends_at ? ` · until ${formatDate(s.ends_at)}` : ''}</span>
                  )).reduce<JSX.Element[]>((acc, el, i) => (i ? [...acc, <span key={`sep-${i}`} className="faint">·</span>, el] : [el]), [])
                  : <span>You're on the free tools. Unlock more with a plan.</span>}
              </span>
              <Link className="btn btn-secondary btn-sm" to="/plans/">{q.data.can_manage_plans ? 'Manage plans' : 'View plans'}</Link>
            </div>
          )}
          {/* everything the user can open sits in one grid, so a few tools don't leave half-empty rows */}
          {(dashboards.length > 0 || q.data.apps.length > 0) && <div className="au-select-label">Your tools</div>}
          <div className="au-options">
            {dashboards.map((o) => {
              const t = q.data!.dashboards?.[o.key]; // name / description / features are edited in the admin
              return (
                <a key={o.key} href={o.to} className={`au-option ${going === o.to ? 'is-going' : ''}`} onClick={(e) => go(e, o.to)}>
                  <div className="au-option-icon">{o.icon}</div>
                  <h2>{t?.name || o.title}</h2>
                  <p>{t?.description || o.description}</p>
                  <ul>{(t?.features.length ? t.features : o.features).map((f) => <li key={f}><Check size={13} /> {f}</li>)}</ul>
                </a>
              );
            })}
            {q.data.apps.map((a) => (
              <a key={a.key} href={a.url} target="_blank" rel="noopener noreferrer"
                className={`au-option au-option-app ${going === a.key ? 'is-going' : ''}`} onClick={(e) => launch(e, a.key)}>
                <div className="au-option-icon"><ToolIcon icon={a.icon} /></div>
                <h2 className="row-tight">{a.name} <ExternalLink size={14} className="faint" /></h2>
                <p>{a.description}</p>
                <ul>{a.features.map((f) => <li key={f}><Check size={13} /> {f}</li>)}</ul>
                <span className="au-option-note">Opens in a new tab · {a.sso ? 'signed in with your TuraVector account' : 'sign in with your account for this application'}</span>
              </a>
            ))}
          </div>

          {q.data.locked_tools.length > 0 && (
            <>
              <div className="au-select-label">More tools</div>
              <div className="au-options">
                {q.data.locked_tools.map((t) => {
                  const inner = (
                    <>
                      <div className="au-option-icon"><ToolIcon icon={t.icon} /></div>
                      <h2 className="row-tight">{t.name} <Lock size={14} className="faint" /></h2>
                      <p>{t.description}</p>
                      {t.features.length > 0 && <ul>{t.features.slice(0, 3).map((f) => <li key={f}><Check size={13} /> {f}</li>)}</ul>}
                      <span className="au-option-note">
                        {t.from_price > 0 ? `From ${money(t.from_price, t.currency)} + GST · ${t.from_period}` : 'Included in a free plan'}
                        {' · '}{q.data!.can_manage_plans ? 'See plans →' : 'Ask your administrator'}
                      </span>
                    </>
                  );
                  return q.data!.can_manage_plans
                    ? <Link key={t.key} to={`/plans/?tool=${t.key}`} className="au-option au-option-locked">{inner}</Link>
                    : <div key={t.key} className="au-option au-option-locked">{inner}</div>;
                })}
              </div>
            </>
          )}
        </div>
      )}
    </BareFrame>
  );
}
