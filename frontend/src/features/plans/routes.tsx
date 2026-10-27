import { lazy } from 'react';
import type { AppRoute } from '@/routes';

const PlansPage = lazy(() => import('./PlansPage'));
const InvoicePage = lazy(() => import('./InvoicePage'));

export const routes: AppRoute[] = [
  { path: '/plans/', element: <PlansPage />, layout: 'bare' },
  { path: '/plans/invoices/:id/', element: <InvoicePage />, layout: 'bare' },
];
