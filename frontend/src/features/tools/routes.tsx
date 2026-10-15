import { lazy } from 'react';
import type { AppRoute } from '@/routes';
import { MovedToSuperadmin } from '@/components/MovedToSuperadmin';

const OtherDocumentsDashboardPage = lazy(() => import('./OtherDocumentsDashboardPage'));
const AnalyticsPage = lazy(() => import('./AnalyticsPage'));
const ExportDataPage = lazy(() => import('./ExportDataPage'));
const JournalSelectorPage = lazy(() => import('./JournalSelectorPage'));
const ConferenceSelectorPage = lazy(() => import('./ConferenceSelectorPage'));

const kinds = ['document-types', 'countries', 'brands', 'therapeutic-areas'] as const;

/** Manage Categories and Mail (logs + SMTP) moved to the superadmin; old URLs forward there. */
const MOVED = [
  ...kinds.flatMap((k) => [
    `/documents/categories/${k}/`, `/documents/categories/${k}/add/`, `/documents/categories/${k}/edit/:itemId/`,
    `/documents/bulk-import/${k}/`,
  ]),
  '/documents/categories/countries/upload/',
  '/documents/mail-logs/', '/documents/mail-logs/:emailLogId/',
  '/documents/smtp-settings/', '/documents/smtp-settings/add/', '/documents/smtp-settings/edit/:smtpId/',
];

/**
 * documents/urls.py paths. Dashboard, analytics, export, journal and conference selector
 * extend other_documents_base.html → 'other'.
 */
export const routes: AppRoute[] = [
  { path: '/journal-selector/dashboard/', element: <OtherDocumentsDashboardPage />, layout: 'other' },
  { path: '/journal-selector/analytics/', element: <AnalyticsPage />, layout: 'other' },
  { path: '/journal-selector/export-data/', element: <ExportDataPage />, layout: 'other' },
  { path: '/journal-selector/journals/', element: <JournalSelectorPage />, layout: 'other' },
  { path: '/journal-selector/conference-selector/', element: <ConferenceSelectorPage />, layout: 'other' },
  ...MOVED.map((path): AppRoute => ({ path, element: <MovedToSuperadmin />, layout: 'bare' })),
];
