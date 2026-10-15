import { lazy } from 'react';
import type { AppRoute } from '@/routes';

const OrganisationPage = lazy(() => import('./OrganisationPage'));
const MemberDetailPage = lazy(() => import('./MemberDetailPage'));
const ReviewerDetailPage = lazy(() => import('./ReviewerDetailPage'));

export const routes: AppRoute[] = [
  { path: '/content-lab-management/organisation/', element: <OrganisationPage />, layout: 'main' },
  { path: '/content-lab-management/organisation/members/:userId/', element: <MemberDetailPage />, layout: 'main' },
  { path: '/content-lab-management/organisation/reviewers/:userId/', element: <ReviewerDetailPage />, layout: 'main' },
];
