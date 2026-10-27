import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { AppWindow, BadgeIndianRupee, Bell, Blocks, Building2, ChevronDown, CreditCard, ExternalLink, Globe2, KeyRound, Landmark, LayoutDashboard, LifeBuoy, LogOut, Mail, Menu, MessageSquare, MessageSquareText, ReceiptIndianRupee, ReceiptText, Repeat, Settings2, Shield, ShieldAlert, Tags, Users, X } from 'lucide-react';
import { useAuth, useUser } from '@/lib/auth';
import { SMTP_SETTINGS_PATH, useIndex } from '@/lib/admin';
import { initials } from '@/lib/format';
import { ThemePicker } from '@/components/ThemePicker';

/** URL of the user-facing app ("View site" in Django's admin header). */
export const SITE_URL: string = (import.meta.env.VITE_SITE_URL as string | undefined) || 'http://localhost:5173';

/** Not listed as tables in the sidebar: workspace data opened from an organisation's tabs (Documents, References,
 * More data…), models with their own sidebar item and the categories. The pages still work by URL. */
const OPENED_FROM_ORGANISATIONS = new Set([
  'documents.AnnotationActivity', 'documents.DocumentAnnotation', 'documents.DocumentReference',
  'documents.DocumentSharing', 'documents.DocumentVersionReference', 'documents.DocumentVersionSharing',
  'documents.DocumentVersion', 'documents.Document', 'documents.EnrollUser', 'documents.Project',
  'library.AssignedReviewer', 'library.DocumentHistory', 'library.ReferenceDocument', 'library.ReferenceZip',
  // own sidebar items / under Manage Categories
  'authentication.ContactQuery', 'documents.EmailLog', 'documents.Feedback', 'documents.Notification', 'documents.Support',
  'documents.Brand', 'documents.Country', 'documents.CourseCategory', 'documents.DocumentType', 'documents.Journal',
  'documents.TherapeuticArea', 'documents.UserJournalSelection',
]);

/** Shown under another app group than the one Django gave them. */
const MOVED_TO_GROUP: Record<string, string> = { 'library.TemporaryPassword': 'authentication' };

function AppNav({ onNavigate }: { onNavigate: () => void }) {
  const { data } = useIndex();
  const location = useLocation();
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const all = (data?.apps ?? []).flatMap((a) => a.models).filter((m) => !OPENED_FROM_ORGANISATIONS.has(m.label));
  const apps = (data?.apps ?? [])
    .map((a) => ({
      ...a,
      models: all.filter((m) => (MOVED_TO_GROUP[m.label] ?? m.app) === a.app_label)
        .sort((x, y) => x.name.localeCompare(y.name)),
    }))
    .filter((a) => a.models.length > 0);
  return (
    <>
      {apps.map((app) => {
        const active = app.models.some((m) => location.pathname.startsWith(`/${m.app}/${m.model}/`));
        const isClosed = closed[app.app_label] ?? false;
        return (
          <div className="nav-group" key={app.app_label}>
            <button className={`nav-link ${active ? 'active' : ''}`} aria-expanded={!isClosed}
              onClick={() => setClosed((c) => ({ ...c, [app.app_label]: !isClosed }))}>
              <span className="grow truncate">{app.name}</span>
              <ChevronDown size={13} style={{ transform: isClosed ? 'rotate(-90deg)' : undefined }} />
            </button>
            {!isClosed && (
              <div className="nav-sub">
                {app.models.map((m) => (
                  <NavLink key={m.label} to={`/${m.app}/${m.model}/`} onClick={onNavigate}
                    className={({ isActive }) => `nav-link nav-link-sub ${isActive || location.pathname.startsWith(`/${m.app}/${m.model}/`) ? 'active' : ''}`}>
                    <span className="grow truncate">{m.name}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

function UserMenu() {
  const user = useUser();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  return (
    <div className="pop-wrap" ref={ref}>
      <button className="user-chip" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
        <span className="avatar">{initials(user.full_name || user.username)}</span>
        <span className="hide-sm" style={{ textAlign: 'left' }}>
          <span className="small" style={{ display: 'block', fontWeight: 500 }}>{user.username}</span>
          <span className="tiny faint">Superuser</span>
        </span>
        <ChevronDown size={13} />
      </button>
      {open && (
        <div className="pop" role="menu">
          <a className="pop-item" href={SITE_URL} target="_blank" rel="noreferrer"><ExternalLink size={14} /> View site</a>
          <Link className="pop-item" to={`/authentication/user/${user.id}/password/`} onClick={() => setOpen(false)}><KeyRound size={14} /> Change password</Link>
          <div className="pop-sep" />
          <button className="pop-item" style={{ color: 'var(--danger)' }} onClick={async () => { await logout(); navigate('/login/'); }}><LogOut size={14} /> Log out</button>
        </div>
      )}
    </div>
  );
}

type MenuItem = { label: string; icon: ReactNode; to?: string; match?: string[]; children?: { label: string; to: string; match?: string[] }[] };

/** Main pages. Everything of one university / organisation lives on its Organisations page (tabs). */
const MAIN_MENU: MenuItem[] = [
  { label: 'Organisations', icon: <Building2 size={16} />, to: '/organisations/' },
  { label: 'All Users', icon: <Users size={16} />, to: '/library/manage-users/',
    match: ['/library/manage-users/', '/library/create-user/', '/library/bulk-import-users/', '/library/user/'] },
  { label: 'Invoices', icon: <ReceiptText size={16} />, to: '/invoices/' },
  { label: 'Subscriptions', icon: <Repeat size={16} />, to: '/subscriptions/' },
  { label: 'Contact Queries', icon: <MessageSquare size={16} />, to: '/authentication/contactquery/' },
  { label: 'Email Logs', icon: <Mail size={16} />, to: '/documents/mail-logs/', match: ['/documents/mail-logs/', '/documents/emaillog/'] },
  { label: 'Feedback', icon: <MessageSquareText size={16} />, to: '/documents/feedback/' },
  { label: 'Notifications', icon: <Bell size={16} />, to: '/documents/notification/' },
  { label: 'Supports', icon: <LifeBuoy size={16} />, to: '/documents/support/' },
];

/** Platform-wide settings: the same for every workspace. */
const PLATFORM_MENU: MenuItem[] = [
  { label: 'Permissions Management', icon: <Shield size={16} />, to: '/library/permissions/dashboard/',
    match: ['/library/permissions/', '/library/roles/', '/library/role/'] },
  { label: 'Tools & Services', icon: <Blocks size={16} />, to: '/tools/' },
  { label: 'Plans & Pricing', icon: <BadgeIndianRupee size={16} />, to: '/plans/' },
  { label: 'Application Access', icon: <AppWindow size={16} />, to: '/app-access/' },
  { label: 'Manage Categories', icon: <Tags size={16} />, children: [
    { label: 'Document Types', to: '/documents/categories/document-types/', match: ['/documents/categories/document-types/', '/documents/bulk-import/document-types/'] },
    { label: 'Countries', to: '/documents/categories/countries/', match: ['/documents/categories/countries/', '/documents/bulk-import/countries/'] },
    { label: 'Brands', to: '/documents/categories/brands/', match: ['/documents/categories/brands/', '/documents/bulk-import/brands/'] },
    { label: 'Therapeutic Areas', to: '/documents/categories/therapeutic-areas/', match: ['/documents/categories/therapeutic-areas/', '/documents/bulk-import/therapeutic-areas/'] },
    { label: 'Course Categories', to: '/documents/coursecategory/' },
    { label: 'Journals', to: '/documents/journal/' },
    { label: 'User Journal Selections', to: '/documents/userjournalselection/' },
    { label: 'User Types', to: '/library/user-types/', match: ['/library/user-types/', '/library/user-type/'] },
  ] },
  { label: 'SMTP Settings', icon: <Mail size={16} />, to: '/documents/smtp-settings/' },
  { label: 'Payment Gateways', icon: <CreditCard size={16} />, to: '/payment-gateways/' },
  { label: 'Rate Cards', icon: <ReceiptIndianRupee size={16} />, to: '/rate-cards/' },
  { label: 'Billing Settings', icon: <Landmark size={16} />, to: '/billing-settings/' },
];

function ManagementNav({ items }: { items: MenuItem[] }) {
  const { pathname } = useLocation();
  const hit = (to: string, match?: string[]) => (match ?? [to]).some((m) => pathname.startsWith(m));
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <>
      {items.map((item) => {
        if (!item.children) {
          return (
            <Link key={item.label} to={item.to!} className={`nav-link ${hit(item.to!, item.match) ? 'active' : ''}`}>
              {item.icon}<span className="grow">{item.label}</span>
            </Link>
          );
        }
        const active = item.children.some((c) => hit(c.to, c.match));
        const isOpen = open[item.label] ?? active;
        return (
          <div className="nav-group" key={item.label}>
            <button className={`nav-link ${active ? 'active' : ''}`} aria-expanded={isOpen} onClick={() => setOpen((o) => ({ ...o, [item.label]: !isOpen }))}>
              {item.icon}<span className="grow">{item.label}</span>
              <ChevronDown size={13} style={{ transform: isOpen ? 'rotate(180deg)' : undefined }} />
            </button>
            {isOpen && (
              <div className="nav-sub">
                {item.children.map((c) => (
                  <Link key={c.to} to={c.to} className={`nav-link nav-link-sub ${hit(c.to, c.match) ? 'active' : ''}`}><span className="grow">{c.label}</span></Link>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

/** One line above a list saying whose data it shows. */
export function ScopeBanner({ scope }: { scope: 'workspace' | 'platform' }) {
  return (
    <div className="ws-banner">
      {scope === 'workspace'
        ? <><Building2 size={14} /> Showing <strong>all workspaces</strong>. To see one university or organisation, open it under <Link className="act" to="/organisations/">Organisations</Link>.</>
        : <><Globe2 size={14} /> Platform-wide: the same for every workspace.</>}
    </div>
  );
}

export function AdminShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMobileOpen(false), [location.pathname]);
  return (
    <div className={`shell ${mobileOpen ? 'is-nav-open' : ''}`}>
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className="sidebar" aria-label="Administration">
        <div className="sidebar-head between">
          <Link to="/" className="logo">Tura<span className="logo-mark">Vector</span> <span className="logo-sub">Admin</span></Link>
          <button className="btn btn-ghost btn-icon mobile-only" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={16} /></button>
        </div>
        <nav className="nav">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><LayoutDashboard size={16} /><span className="grow">Dashboard</span></NavLink>
        </nav>
        <nav className="nav"><ManagementNav items={MAIN_MENU} /></nav>
        <div className="sidebar-section-label">Platform settings</div>
        <nav className="nav">
          <ManagementNav items={PLATFORM_MENU} />
          <NavLink to="/timezone-management/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Globe2 size={16} /><span className="grow">Timezone Management</span></NavLink>
          <NavLink to="/settings/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Settings2 size={16} /><span className="grow">System Settings</span></NavLink>
        </nav>
        <nav className="nav"><AppNav onNavigate={() => setMobileOpen(false)} /></nav>
      </aside>
      <div className="shell-main">
        <header className="topbar">
          <div className="topbar-inner">
            <button className="btn btn-ghost btn-icon mobile-only" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu size={18} /></button>
            <div className="topbar-right">
              <ThemePicker />
              <UserMenu />
            </div>
          </div>
        </header>
        <main id="main" className="page">{children}</main>
        <footer className="app-footer">
          <span>TuraVector site administration</span>
          <a href={SITE_URL} target="_blank" rel="noreferrer">View site</a>
        </footer>
      </div>
      <div className="shell-scrim" onClick={() => setMobileOpen(false)} />
    </div>
  );
}

/** Shown to authenticated users without is_superuser. */
export function NoAccess() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="auth-wrap">
      <div className="panel auth-card">
        <div className="panel-body stack">
          <div className="row"><ShieldAlert size={20} style={{ color: 'var(--danger)' }} /><h1 style={{ fontSize: 22 }}>Superuser access required</h1></div>
          <p className="muted">
            You are authenticated as <strong>{user?.username}</strong>, but are not authorized to access this page.
            Only superusers can use the TuraVector administration site.
          </p>
          <div className="row">
            <button className="btn btn-primary" onClick={async () => { await logout(); navigate('/login/'); }}>Log in as another user</button>
            <a className="btn btn-secondary" href={SITE_URL}>Go to TuraVector</a>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Django-style breadcrumbs: Home › App › Model › Object › Action */
export function Crumbs({ items }: { items: { label: ReactNode; to?: string }[] }) {
  const { pathname } = useLocation();
  // SMTP Settings sits in the sidebar's Settings section, not under the Documents app
  if (pathname.startsWith(SMTP_SETTINGS_PATH)) {
    items = items.map((it) => (it.to === '/documents/' ? { label: 'Settings' } : it));
  }
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <Link to="/">Home</Link>
      {items.map((it, i) => (
        <span key={i} className="row-tight">
          <span className="faint" aria-hidden>›</span>
          {it.to ? <Link to={it.to}>{it.label}</Link> : <span className="muted">{it.label}</span>}
        </span>
      ))}
    </nav>
  );
}
