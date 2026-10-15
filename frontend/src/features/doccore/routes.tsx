import { lazy } from 'react';
import { Navigate } from 'react-router-dom';
import type { AppRoute } from '@/routes';
import { useAuth } from '@/lib/auth';
import { MovedToSuperadmin } from '@/components/MovedToSuperadmin';

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const ManagerDashboard = lazy(() => import('@/features/users/pages/ManagerDashboard'));
const FinanceDashboard = lazy(() => import('@/features/billing/FinanceDashboard'));

/** One "Dashboard": managers and workspace admins get the team view, everyone else their own. */
function ContentLabDashboard() {
  const { can, user } = useAuth();
  if (can('can_access_manager_dashboard')) return <ManagerDashboard />;
  // a Turacoz Financial Manager without a document dashboard lands on the Finance dashboard
  if (user?.is_invoice_approver && !can('can_access_dashboard')) {
    return can('can_access_reviewer_dashboard') ? <Navigate to="/content-lab-management/reviewer-dashboard/" replace /> : <FinanceDashboard />;
  }
  return <DashboardPage />;
}
const ReviewerDashboardPage = lazy(() => import('./pages/ReviewerDashboardPage'));
const AllReviewsPage = lazy(() => import('./pages/AllReviewsPage'));
const ReviewerAssignmentsPage = lazy(() => import('./pages/ReviewerAssignmentsPage'));
const UploadPage = lazy(() => import('./pages/UploadPage'));
const UploadLegacyPage = lazy(() => import('./pages/UploadLegacyPage'));
const NewVersionPage = lazy(() => import('./pages/NewVersionPage'));
const DocumentDetailPage = lazy(() => import('./pages/DocumentDetailPage'));
const DocumentEditPage = lazy(() => import('./pages/DocumentEditPage'));
const DocumentHistoryPage = lazy(() => import('./pages/DocumentHistoryPage'));
const ReferencesPage = lazy(() => import('./pages/ReferencesPage'));
const LegacyPlaceholderPage = lazy(() => import('./pages/LegacyPlaceholderPage'));

const main = (path: string, element: JSX.Element): AppRoute => ({ path, element, layout: 'main' });

export const routes: AppRoute[] = [
  // content_lab_dashboard_view (its old aliases home/, list/, user-home/... forward here via lib/legacyPaths)
  main('/content-lab-management/dashboard/', <ContentLabDashboard />),
  main('/content-lab-management/reviewer-dashboard/', <ReviewerDashboardPage />),
  main('/content-lab-management/all-reviews/', <AllReviewsPage />),
  main('/content-lab-management/reviewer-assignments/', <ReviewerAssignmentsPage />),

  // upload
  main('/content-lab-management/upload/', <UploadPage />),
  main('/content-lab-management/main-document/', <UploadPage />),
  main('/content-lab-management/upload-legacy/', <UploadLegacyPage />),

  // document lifecycle
  main('/content-lab-management/document/:documentId/', <DocumentDetailPage />),
  main('/content-lab-management/document/:documentId/edit/', <DocumentEditPage />),
  main('/content-lab-management/document/:documentId/new-version/', <NewVersionPage />),
  // staff-only status updates and file replacement moved to the superadmin
  { path: '/documents/document/:documentId/update-status/', element: <MovedToSuperadmin />, layout: 'bare' },
  { path: '/documents/version/:versionId/update-status/', element: <MovedToSuperadmin />, layout: 'bare' },
  { path: '/documents/version/:versionId/change-file/', element: <MovedToSuperadmin to={(p) => p.replace(/^\/documents\/version\/(\d+)\/change-file\/$/, '/documents/documentversion/$1/change-file/')} />, layout: 'bare' },

  // history
  main('/content-lab-management/history/', <DocumentHistoryPage />),
  main('/content-lab-management/history/:documentId/', <DocumentHistoryPage />),
  main('/content-lab-management/document/:documentId/history/', <DocumentHistoryPage source="library" />),

  // document references (ZIP)
  main('/content-lab-management/references/', <ReferencesPage />),

  // legacy views whose templates do not exist in the Django project
  main('/content-lab-management/references/:documentId/', <LegacyPlaceholderPage title="Reference History" />),
  main('/content-lab-management/reference-document/', <LegacyPlaceholderPage title="Upload Reference Document" />),
  main('/content-lab-management/document-for-review/', <LegacyPlaceholderPage title="Documents for Review" />),
  main('/content-lab-management/upload-version/', <LegacyPlaceholderPage title="Upload Version" />),
  main('/content-lab-management/upload-reference-zip/', <LegacyPlaceholderPage title="Upload Reference ZIP" />),
  main('/content-lab-management/complete/', <LegacyPlaceholderPage title="Complete Document" needsVersionId />),
  main('/content-lab-management/enable-editing/', <LegacyPlaceholderPage title="Enable Editing" needsVersionId />),
];
