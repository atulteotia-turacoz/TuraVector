/**
 * The two authenticated layouts of the original app:
 *  - "main"  ⇐ templates/base.html  (Content Review sidebar, quick stats, notification bell)
 *  - "other" ⇐ templates/other_documents_base.html (Other Documents sidebar)
 * Menu items and their permission gates are copied one-for-one from those templates.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Archive, ArrowLeftRight, BarChart3, Landmark, ReceiptText, Bell, BookOpen, Building2, ChevronDown, CreditCard, Gauge, Library, LifeBuoy, LineChart, LogOut, Menu, Presentation, Shield, Upload, User, UserCheck, X,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth, useUser } from '@/lib/auth';
import { ThemePicker } from '@/components/ThemePicker';
import { WorkspaceLogo } from '@/components/WorkspaceLogo';
import { initials } from '@/lib/format';
import { useTimezoneAutoDetect } from '@/features/auth/utils';

interface NavItem { to: string; label: string; icon: ReactNode; badge?: string; show: boolean; children?: NavItem[] }

function useMainNav(): NavItem[] {
  const user = useUser();
  const { can } = useAuth();
  return [
    { to: '/content-lab-management/dashboard/', label: 'Dashboard', icon: <Gauge size={16} />, show: can('can_access_dashboard') || can('can_access_manager_dashboard') },
    { to: '/content-lab-management/reviewer-dashboard/', label: 'Reviewer Dashboard', icon: <UserCheck size={16} />, badge: 'REV', show: can('can_access_reviewer_dashboard') },
    { to: '/content-lab-management/upload/', label: 'Upload Document', icon: <Upload size={16} />, show: can('can_upload') },
    { to: '/content-lab-management/library/', label: 'Document Library', icon: <Library size={16} />, show: can('can_access_library') },
    { to: '/content-lab-management/reference-library/', label: 'References', icon: <Archive size={16} />, show: can('can_access_references') },
    { to: '/content-lab-management/references/', label: 'Document References', icon: <BookOpen size={16} />, show: can('can_access_document_references') },
    { to: '/content-lab-management/finance/', label: 'Finance Dashboard', icon: <Landmark size={16} />, badge: 'FIN', show: !!user.is_invoice_approver },
    { to: '/content-lab-management/finance/reports/', label: 'Finance Reports', icon: <BarChart3 size={16} />, show: !!user.is_invoice_approver || user.is_org_admin },
    { to: '/content-lab-management/invoices/', label: 'Invoices', icon: <ReceiptText size={16} />, show: user.is_org_admin || !!user.is_invoice_approver },
    { to: '/content-lab-management/my-requests/', label: 'My Requests', icon: <ReceiptText size={16} />,
      show: !user.is_org_admin && !user.is_invoice_approver && (user.organisation?.kind === 'university' || user.organisation?.kind === 'organisation') },
    { to: '/content-lab-management/organisation/', label: user.organisation?.kind === 'organisation' ? 'Organisation' : 'University', icon: <Building2 size={16} />, badge: 'ADMIN', show: user.is_org_admin },
    { to: '/profile/', label: 'Profile', icon: <User size={16} />, show: true },
  ];
}

function useOtherNav(): NavItem[] {
  const user = useUser();
  return [
    { to: '/journal-selector/dashboard/', label: 'Dashboard', icon: <Gauge size={16} />, show: true },
    { to: '/journal-selector/journals/', label: 'Journal Selector', icon: <BookOpen size={16} />, show: true },
    { to: '/journal-selector/conference-selector/', label: 'Conference Selector', icon: <Presentation size={16} />, show: true },
    { to: '/journal-selector/analytics/', label: 'Analytics', icon: <LineChart size={16} />, show: true },
    { to: '/journal-selector/export-data/', label: 'Reports', icon: <BarChart3 size={16} />, show: user.is_manager_like },
  ];
}

function NavGroup({ item, onNavigate }: { item: NavItem; onNavigate: () => void }) {
  const location = useLocation();
  const active = item.children?.some((c) => location.pathname.startsWith(c.to)) ?? false;
  const [open, setOpen] = useState(active);
  return (
    <div className="nav-group">
      <button className={`nav-link ${active ? 'active' : ''}`} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {item.icon}<span className="grow">{item.label}</span>
        {item.badge && <span className="nav-badge">{item.badge}</span>}
        <ChevronDown size={13} style={{ transform: open ? 'rotate(180deg)' : undefined }} />
      </button>
      {open && (
        <div className="nav-sub">
          {item.children!.filter((c) => c.show).map((c) => (
            <NavLink key={c.to} to={c.to} onClick={onNavigate} className={({ isActive }) => `nav-link nav-link-sub ${isActive ? 'active' : ''}`}>{c.icon}<span>{c.label}</span></NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

function QuickStats() {
  const { data } = useQuery({
    queryKey: ['quick-stats'],
    queryFn: async () => (await api.get('/api/library/quick-stats')).data.data as { total_documents: number; total_references: number; zip_references: number },
  });
  return (
    <div className="quick-stats">
      <div className="pop-head" style={{ padding: '0 0 6px' }}>Quick stats</div>
      <div className="between small"><span className="muted">Documents</span><strong>{data?.total_documents ?? '–'}</strong></div>
      <div className="between small"><span className="muted">References</span><strong>{data?.total_references ?? '–'}</strong></div>
      <div className="between small"><span className="muted">ZIP References</span><strong>{data?.zip_references ?? '–'}</strong></div>
    </div>
  );
}

interface NotificationRow { id: number; type: string; description: string; document_id: number; sender: string; is_seen: boolean; time_ago: string }

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ['notifications', 'recent'],
    queryFn: async () => (await api.get('/api/notifications/recent')).data as { notifications: NotificationRow[]; unread_count: number },
    refetchInterval: 30000,
  });
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const markRead = async (id: number) => {
    await api.post(`/api/notifications/${id}/read`);
    void qc.invalidateQueries({ queryKey: ['notifications'] });
  };
  const count = data?.unread_count ?? 0;
  return (
    <div className="pop-wrap" ref={ref}>
      <button className="btn btn-ghost btn-icon bell" aria-label={`Notifications (${count} unread)`} onClick={() => setOpen((o) => !o)}>
        <Bell size={16} />{count > 0 && <span className="bell-count">{count > 99 ? '99+' : count}</span>}
      </button>
      {open && (
        <div className="pop notif-pop">
          <div className="pop-head between"><span>Notifications</span><span>{count} unread</span></div>
          {(data?.notifications ?? []).slice(0, 5).map((n) => (
            <button key={n.id} className="pop-item notif-item" onClick={() => {
              if (!n.is_seen) void markRead(n.id);
              if (n.type === 'invoice') { setOpen(false); navigate(`/content-lab-management/invoices/${n.document_id}/`); }
            }}>
              <span className="grow" style={{ minWidth: 0 }}>
                <span className="truncate" style={{ display: 'block', fontWeight: n.is_seen ? 400 : 600 }} title={n.description}>{n.description}</span>
                <span className="tiny faint">{n.time_ago}</span>
              </span>
              {!n.is_seen && <span className="badge badge-accent">New</span>}
            </button>
          ))}
          {(data?.notifications?.length ?? 0) === 0 && <div className="pop-item muted">No notifications</div>}
          <div className="pop-sep" />
          <Link className="pop-item" to="/content-lab-management/notifications/" onClick={() => setOpen(false)}>View all</Link>
        </div>
      )}
    </div>
  );
}

export function UserMenu({ profilePath }: { profilePath: string }) {
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
      <button className="user-chip" onClick={() => setOpen((o) => !o)}>
        <span className="avatar">{initials(user.full_name)}</span>
        <span className="hide-sm" style={{ textAlign: 'left' }}>
          <span className="small" style={{ display: 'block', fontWeight: 500 }}>{user.full_name}</span>
          <span className="tiny faint">{user.user_type_display}</span>
        </span>
        <ChevronDown size={13} />
      </button>
      {open && (
        <div className="pop">
          <Link className="pop-item" to={profilePath} onClick={() => setOpen(false)}><User size={14} /> Profile</Link>
          {(user.organisation?.kind === 'individual' || user.is_org_admin) && (
            <Link className="pop-item" to="/plans/" onClick={() => setOpen(false)}><CreditCard size={14} /> Plans &amp; billing</Link>
          )}
          <Link className="pop-item" to="/content-lab-management/notifications/" onClick={() => setOpen(false)}><Bell size={14} /> Notifications</Link>
          <Link className="pop-item" to="/content-lab-management/help-support/" onClick={() => setOpen(false)}><LifeBuoy size={14} /> Help &amp; Support</Link>
          <div className="pop-sep" />
          <button className="pop-item" style={{ color: 'var(--danger)' }} onClick={async () => { await logout(); navigate('/'); }}><LogOut size={14} /> Logout</button>
        </div>
      )}
    </div>
  );
}

export function AppShell({ variant, children }: { variant: 'main' | 'other'; children: ReactNode }) {
  useTimezoneAutoDetect(); // base.html loaded timezone_detection.js on every page
  const mainNav = useMainNav();
  const otherNav = useOtherNav();
  const nav = variant === 'main' ? mainNav : otherNav;
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className={`shell ${mobileOpen ? 'is-nav-open' : ''}`}>
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className="sidebar" aria-label="Primary">
        <div className="sidebar-head between">
          <WorkspaceLogo />
          <button className="btn btn-ghost btn-icon mobile-only" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={16} /></button>
        </div>
        {variant === 'other' && <div className="sidebar-section-label">Other Documents</div>}
        <Link to="/home" className="btn btn-secondary btn-block switch-btn"><ArrowLeftRight size={14} /> Home</Link>
        <nav className="nav">
          {nav.filter((i) => i.show).map((item) => item.children
            ? <NavGroup key={item.to} item={item} onNavigate={() => setMobileOpen(false)} />
            : (
              <NavLink key={item.to} to={item.to} end={item.to === '/content-lab-management/library/' || item.to === '/content-lab-management/finance/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                {item.icon}<span className="grow">{item.label}</span>{item.badge && <span className="nav-badge">{item.badge}</span>}
              </NavLink>
            ))}
        </nav>
        {variant === 'main' && <QuickStats />}
      </aside>
      <div className="shell-main">
        <header className="topbar">
          <div className="topbar-inner">
            <button className="btn btn-ghost btn-icon mobile-only" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu size={18} /></button>
            <div className="topbar-right">
              <ThemePicker />
              <NotificationBell />
              <UserMenu profilePath={variant === 'other' ? '/journal-selector/profile/' : '/profile/'} />
            </div>
          </div>
        </header>
        <main id="main" className="page">{children}</main>
        <footer className="app-footer">
          <span>© {new Date().getFullYear()} TuraVector</span>
          <span className="row">
            <Link to="/documents/terms-and-conditions/">Terms &amp; Conditions</Link>
            <Link to="/documents/privacy-policy/">Privacy Policy</Link>
          </span>
        </footer>
      </div>
      <div className="shell-scrim" onClick={() => setMobileOpen(false)} />
    </div>
  );
}
