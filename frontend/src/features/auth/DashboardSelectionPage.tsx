/** Port of templates/documents/dashboard_selection.html (dashboard_selection_view). Standalone page. */
import { useEffect, useState, type MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BookOpenCheck, Brain, Check, ExternalLink, FileText, FlaskConical, GraduationCap, SpellCheck } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { useUser } from '@/lib/auth';
import { ErrorNotice, Loading, useToast } from '@/components/ui';
import { ThemePicker } from '@/components/ThemePicker';
import { NotificationBell, UserMenu } from '@/layouts/AppShell';
import { BareFrame } from './components';
import { useTimezoneAutoDetect } from './utils';
import './auth.css';

interface Selection {
  can_access_content_lab: boolean;
  can_access_other_documents: boolean;
  apps: { key: string; name: string; description: string; features: string[]; url: string; sso: boolean }[];
  redirect: string | null;
  error: string | null;
}

const APP_ICONS: Record<string, JSX.Element> = {
  ext_research_assistant: <Brain size={22} />,
  ext_lms: <GraduationCap size={22} />,
  ext_turagrammar: <SpellCheck size={22} />,
};

const OPTIONS = [
  {
    key: 'content_lab' as const,
    to: '/content-lab-management/dashboard/',
    icon: <FlaskConical size={22} />,
    title: 'Content Lab Management',
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
          {(q.data.can_access_content_lab || q.data.can_access_other_documents) && (
            <div className="au-select-label">TuraVector</div>
          )}
          <div className="au-options">
            {OPTIONS.filter((o) => (o.key === 'content_lab' ? q.data!.can_access_content_lab : q.data!.can_access_other_documents)).map((o) => (
              <a key={o.key} href={o.to} className={`au-option ${going === o.to ? 'is-going' : ''}`} onClick={(e) => go(e, o.to)}>
                <div className="au-option-icon">{o.icon}</div>
                <h2>{o.title}</h2>
                <p>{o.description}</p>
                <ul>{o.features.map((f) => <li key={f}><Check size={13} /> {f}</li>)}</ul>
              </a>
            ))}
          </div>

          {q.data.apps.length > 0 && (
            <>
              <div className="au-select-label">Other Tura applications</div>
              <div className="au-options">
                {q.data.apps.map((a) => (
                  <a key={a.key} href={a.url} target="_blank" rel="noopener noreferrer"
                    className={`au-option au-option-app ${going === a.key ? 'is-going' : ''}`} onClick={(e) => launch(e, a.key)}>
                    <div className="au-option-icon">{APP_ICONS[a.key] ?? <BookOpenCheck size={22} />}</div>
                    <h2 className="row-tight">{a.name} <ExternalLink size={14} className="faint" /></h2>
                    <p>{a.description}</p>
                    <ul>{a.features.map((f) => <li key={f}><Check size={13} /> {f}</li>)}</ul>
                    <span className="au-option-note">Opens in a new tab · {a.sso ? 'signed in with your TuraVector account' : 'sign in with your account for this application'}</span>
                  </a>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </BareFrame>
  );
}
