/** /logout/ — logout_view: log the logout, end the session and go back to the landing page. */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/lib/auth';
import { Loading } from '@/components/ui';

export default function LogoutPage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    (async () => {
      if (user) await logout();
      if (!cancelled) navigate('/', { replace: true });
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);
  return <Loading label="Signing out…" />;
}
