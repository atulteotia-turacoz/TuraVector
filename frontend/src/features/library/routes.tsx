import { lazy } from 'react';
import type { AppRoute } from '@/routes';

const LibraryPage = lazy(() => import('./pages/LibraryPage'));
const ReferenceLibraryPage = lazy(() => import('./pages/ReferenceLibraryPage'));
const ReferenceDetailPage = lazy(() => import('./pages/ReferenceDetailPage'));
const UploadReferencePage = lazy(() => import('./pages/UploadReferencePage'));
const UploadReferenceZipPage = lazy(() => import('./pages/UploadReferenceZipPage'));
const ReferenceZipDetailPage = lazy(() => import('./pages/ReferenceZipDetailPage'));
const AssignReviewerPage = lazy(() => import('./pages/AssignReviewerPage'));
const ManageReviewersPage = lazy(() => import('./pages/ManageReviewersPage'));

export const routes: AppRoute[] = [
  { path: '/content-lab-management/library/', element: <LibraryPage />, layout: 'main' },
  { path: '/content-lab-management/reference-library/', element: <ReferenceLibraryPage />, layout: 'main' },
  { path: '/content-lab-management/reference-library/upload/', element: <UploadReferencePage />, layout: 'main' },
  { path: '/content-lab-management/reference-library/upload-zip/', element: <UploadReferenceZipPage />, layout: 'main' },
  { path: '/content-lab-management/reference-library/:referenceId/', element: <ReferenceDetailPage />, layout: 'main' },
  { path: '/content-lab-management/reference-zip/:zipId/', element: <ReferenceZipDetailPage />, layout: 'main' },
  { path: '/content-lab-management/document/:documentId/assign-reviewer/', element: <AssignReviewerPage />, layout: 'main' },
  { path: '/content-lab-management/document/:documentId/manage-reviewers/', element: <ManageReviewersPage />, layout: 'main' },
];
