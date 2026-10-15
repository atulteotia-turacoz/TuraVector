import { Link } from 'react-router-dom';
import { useAuth } from '@/lib/auth';

/**
 * Brand mark for the signed-in user's workspace: the university/organisation logo and name with a
 * small "TuraVector" underneath. Individual workspaces, superadmins and signed-out pages show TuraVector.
 */
export function WorkspaceLogo({ to }: { to?: string }) {
  const { user } = useAuth();
  to = to ?? (user ? '/home' : '/');
  const org = user?.organisation;
  if (!org || org.kind === 'individual') {
    return <Link to={to} className="logo">Tura<span className="logo-mark">Vector</span></Link>;
  }
  return (
    <Link to={to} className="ws-logo" title={org.name}>
      {org.logo_url
        ? <img src={org.logo_url} alt="" className="ws-logo-img" />
        : <span className="ws-logo-initial" aria-hidden>{org.name.slice(0, 1).toUpperCase()}</span>}
      <span className="ws-logo-text">
        <span className="ws-logo-name truncate">{org.name}</span>
        <span className="ws-logo-sub">on Tura<span className="logo-mark">Vector</span></span>
      </span>
    </Link>
  );
}
