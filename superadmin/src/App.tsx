import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '@/lib/auth';
import { setUserTimeZone } from '@/lib/format';
import { Loading } from '@/components/ui';
import { AdminShell, NoAccess } from '@/components/Shell';
import { managementRoutes } from '@/features/management/routes';

const Login = lazy(() => import('@/pages/Login'));
const Dashboard = lazy(() => import('@/pages/Dashboard'));
const AppIndex = lazy(() => import('@/pages/AppIndex'));
const ChangeList = lazy(() => import('@/pages/ChangeList'));
const ChangeForm = lazy(() => import('@/pages/ChangeForm'));
const DeletePage = lazy(() => import('@/pages/DeletePage'));
const History = lazy(() => import('@/pages/History'));
const UserPassword = lazy(() => import('@/pages/UserPassword'));
const ChangeFile = lazy(() => import('@/pages/ChangeFile'));
const Timezone = lazy(() => import('@/pages/Timezone'));
const SystemSettings = lazy(() => import('@/pages/SystemSettings'));
const AppAccess = lazy(() => import('@/pages/AppAccess'));
const Organisations = lazy(() => import('@/pages/Organisations'));
const PaymentGateways = lazy(() => import('@/pages/PaymentGateways'));
const RateCards = lazy(() => import('@/pages/RateCards'));
const BillingSettings = lazy(() => import('@/pages/BillingSettings'));
const InvoicesList = lazy(() => import('@/pages/Invoices').then((m) => ({ default: m.InvoicesList })));
const InvoiceDetail = lazy(() => import('@/pages/Invoices').then((m) => ({ default: m.InvoiceDetail })));
const TeamMemberDetail = lazy(() => import('@/pages/TeamMemberDetail'));
const OrganisationDetail = lazy(() => import('@/pages/OrganisationDetail'));
const NotFound = lazy(() => import('@/pages/NotFound'));

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to={`/login/?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (!user.is_superuser) return <NoAccess />;
  return <AdminShell><Suspense fallback={<Loading />}>{children}</Suspense></AdminShell>;
}

/** URL layout follows Django's admin: /<app>/<model>/<pk>/change/ etc. */
export default function App() {
  const { user } = useAuth();
  useEffect(() => setUserTimeZone(user?.timezone), [user?.timezone]);
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/login/" element={<Login />} />
        <Route path="/login" element={<Navigate to="/login/" replace />} />
        <Route path="/" element={<Protected><Dashboard /></Protected>} />
        <Route path="/timezone-management/" element={<Protected><Timezone /></Protected>} />
        <Route path="/settings/" element={<Protected><SystemSettings /></Protected>} />
        <Route path="/app-access/" element={<Protected><AppAccess /></Protected>} />
        <Route path="/organisations/" element={<Protected><Organisations /></Protected>} />
        <Route path="/payment-gateways/" element={<Protected><PaymentGateways /></Protected>} />
        <Route path="/rate-cards/" element={<Protected><RateCards /></Protected>} />
        <Route path="/billing-settings/" element={<Protected><BillingSettings /></Protected>} />
        <Route path="/invoices/" element={<Protected><InvoicesList /></Protected>} />
        <Route path="/invoices/:id/" element={<Protected><InvoiceDetail /></Protected>} />
        <Route path="/organisations/:orgId/" element={<Protected><OrganisationDetail /></Protected>} />
        <Route path="/organisations/:orgId/members/:userId/" element={<Protected><TeamMemberDetail /></Protected>} />
        <Route path="/authentication/user/:pk/password/" element={<Protected><UserPassword /></Protected>} />
        <Route path="/documents/documentversion/:pk/change-file/" element={<Protected><ChangeFile /></Protected>} />
        {managementRoutes.map((r) => <Route key={r.path} path={r.path} element={<Protected>{r.element}</Protected>} />)}
        <Route path="/:app/" element={<Protected><AppIndex /></Protected>} />
        <Route path="/:app/:model/" element={<Protected><ChangeList /></Protected>} />
        <Route path="/:app/:model/add/" element={<Protected><ChangeForm /></Protected>} />
        <Route path="/:app/:model/:pk/change/" element={<Protected><ChangeForm /></Protected>} />
        <Route path="/:app/:model/:pk/delete/" element={<Protected><DeletePage /></Protected>} />
        <Route path="/:app/:model/:pk/history/" element={<Protected><History /></Protected>} />
        <Route path="*" element={<Protected><NotFound /></Protected>} />
      </Routes>
    </Suspense>
  );
}
