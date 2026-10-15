import { lazy } from 'react';
import { Navigate } from 'react-router-dom';
import type { AppRoute } from '@/routes';
import { MovedToSuperadmin } from '@/components/MovedToSuperadmin';
import './users.css';

const Reports = lazy(() => import('./pages/Reports'));

/** User Management and Permissions Management moved to the superadmin; old URLs forward there. */
const MOVED = [
  '/library/manage-users/', '/library/create-user/', '/library/bulk-import-users/',
  '/library/user/:userId/view/', '/library/user/:userId/edit/', '/library/user/:userId/change-password/',
  '/library/user/:userId/view-password/', '/library/user/:userId/permissions/',
  '/library/roles/', '/library/role/create/', '/library/role/:roleId/edit/',
  '/library/permissions/dashboard/', '/library/permissions/roles/', '/library/permissions/roles/create/',
  '/library/permissions/roles/:roleId/', '/library/permissions/roles/:roleId/edit/',
  '/library/permissions/users/:userId/roles/', '/library/permissions/users/:userId/permissions/',
  '/library/permissions/dashboard-access/',
  '/library/user-types/', '/library/user-type/create/', '/library/user-type/:userTypeId/edit/',
];

export const routes: AppRoute[] = [
  // the manager dashboard is the Content Lab "Dashboard" for managers (see doccore/routes.tsx); old URL forwards
  { path: '/content-lab-management/manager-dashboard/', element: <Navigate to="/content-lab-management/dashboard/" replace />, layout: 'main' },
  { path: '/content-lab-management/reports/', element: <Reports />, layout: 'main' },
  ...MOVED.map((path): AppRoute => ({ path, element: <MovedToSuperadmin />, layout: 'bare' })),
];
