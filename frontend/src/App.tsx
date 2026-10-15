import { Suspense, useEffect, type ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { legacyToNewPath } from '@/lib/legacyPaths';
import { useAuth } from '@/lib/auth';
import { setUserTimeZone } from '@/lib/format';
import { AppShell } from '@/layouts/AppShell';
import { Empty, Loading } from '@/components/ui';
import type { AppRoute } from '@/routes';

// Collect routes from every feature folder.
const modules = import.meta.glob<{ routes: AppRoute[] }>('./features/*/routes.tsx', { eager: true });
const allRoutes: AppRoute[] = Object.values(modules).flatMap((m) => m.routes ?? []);

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to={`/login/?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return <>{children}</>;
}

function wrap(r: AppRoute) {
  const page = <Suspense fallback={<Loading />}>{r.element}</Suspense>;
  const laidOut = r.layout === 'bare' ? page : <AppShell variant={r.layout}>{page}</AppShell>;
  return r.public ? laidOut : <Protected>{laidOut}</Protected>;
}

function NotFound() {
  const { user } = useAuth();
  const body = <Empty title="Page not found">The page you are looking for does not exist or has moved.</Empty>;
  return user ? <AppShell variant="main">{body}</AppShell> : <div className="auth-wrap">{body}</div>;
}

/** Old /documents/... and /library/... page URLs forward to their new place. */
function LegacyRedirect() {
  const { pathname, search, hash } = useLocation();
  const to = legacyToNewPath(pathname);
  return to && to !== pathname ? <Navigate to={`${to}${search}${hash}`} replace /> : <NotFound />;
}

export default function App() {
  const { user } = useAuth();
  useEffect(() => setUserTimeZone(user?.timezone), [user?.timezone]);
  const hasRoot = allRoutes.some((r) => r.path === '/');
  return (
    <Routes>
      {allRoutes.map((r) => <Route key={r.path} path={r.path} element={wrap(r)} />)}
      {!hasRoot && <Route path="/" element={<Navigate to={user ? '/home' : '/login/'} replace />} />}
      <Route path="/documents/*" element={<LegacyRedirect />} />
      <Route path="/library/*" element={<LegacyRedirect />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
