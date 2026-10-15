import { lazy } from 'react';
import type { AppRoute } from '@/routes';

const InvoicesPage = lazy(() => import('./InvoicesPage'));
const InvoiceDetailPage = lazy(() => import('./InvoiceDetailPage'));
const MyRequestsPage = lazy(() => import('./MyRequestsPage'));
const FinanceDashboard = lazy(() => import('./FinanceDashboard'));
const FinanceReportsPage = lazy(() => import('./FinanceReportsPage'));

export const routes: AppRoute[] = [
  { path: '/content-lab-management/invoices/', element: <InvoicesPage />, layout: 'main' },
  { path: '/content-lab-management/invoices/:id/', element: <InvoiceDetailPage />, layout: 'main' },
  { path: '/content-lab-management/my-requests/', element: <MyRequestsPage />, layout: 'main' },
  { path: '/content-lab-management/finance/', element: <FinanceDashboard />, layout: 'main' },
  { path: '/content-lab-management/finance/reports/', element: <FinanceReportsPage />, layout: 'main' },
];
