import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { SUPERADMIN_URL } from '@/lib/api';
import { Loading } from '@/components/ui';

/**
 * Old user-app URL of something that now lives in the superadmin. By default the path is the
 * same there; `to` maps it when the admin URL differs.
 */
export function MovedToSuperadmin({ to }: { to?: (path: string) => string }) {
  const { pathname, search } = useLocation();
  useEffect(() => {
    window.location.replace(`${SUPERADMIN_URL}${to ? to(pathname) : pathname}${search}`);
  }, [pathname, search, to]);
  return <Loading label="Opening the admin console…" />;
}
