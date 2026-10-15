import { lazy } from 'react';
import type { AppRoute } from '@/routes';

const PreviewPage = lazy(() => import('./pages/PreviewPage'));
const PreviewSimplePage = lazy(() => import('./pages/PreviewSimplePage'));
const ReviewPage = lazy(() => import('./pages/ReviewPage'));
const ReferencePreviewPage = lazy(() => import('./pages/ReferencePreviewPage'));
const CommentsReferencesPage = lazy(() => import('./pages/CommentsReferencesPage'));
const LinkReferencesPage = lazy(() => import('./pages/LinkReferencesPage'));
const OnlyOfficeEditPage = lazy(() => import('./pages/OnlyOfficeEditPage'));
const DraftPage = lazy(() => import('./pages/MiscPages').then((m) => ({ default: m.DraftPage })));
const EditorRedirectPage = lazy(() => import('./pages/MiscPages').then((m) => ({ default: m.EditorRedirectPage })));
const DownloadAnnotatedPage = lazy(() => import('./pages/MiscPages').then((m) => ({ default: m.DownloadAnnotatedPage })));

/** Django URLs of documents/urls.py for the viewer module (all templates extend base.html except the OnlyOffice editor). */
export const routes: AppRoute[] = [
  { path: '/content-lab-management/preview/:versionId/', element: <PreviewPage />, layout: 'main' },
  { path: '/content-lab-management/preview-simple/:versionId/', element: <PreviewSimplePage />, layout: 'main' },
  { path: '/content-lab-management/review/', element: <ReviewPage />, layout: 'main' },
  { path: '/content-lab-management/comments/:versionId/', element: <CommentsReferencesPage />, layout: 'main' },
  { path: '/content-lab-management/draft/', element: <DraftPage />, layout: 'main' },
  { path: '/content-lab-management/draft/:versionId/', element: <DraftPage />, layout: 'main' },
  { path: '/content-lab-management/reference-preview/:referenceId/', element: <ReferencePreviewPage />, layout: 'main' },
  { path: '/content-lab-management/reference-view/', element: <ReferencePreviewPage />, layout: 'main' },
  { path: '/content-lab-management/version/:versionId/link-references/', element: <LinkReferencesPage />, layout: 'main' },
  { path: '/content-lab-management/editor/:versionId/', element: <EditorRedirectPage />, layout: 'main' },
  { path: '/content-lab-management/download/:versionId/annotated/', element: <DownloadAnnotatedPage />, layout: 'main' },
  // OnlyOfficeEditView had no login_required and its template is a standalone HTML page
  { path: '/content-lab-management/onlyoffice/edit/', element: <OnlyOfficeEditPage />, layout: 'bare', public: true },
];
