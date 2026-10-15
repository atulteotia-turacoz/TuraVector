import { lazy } from 'react';
import type { AppRoute } from '@/routes';

const LandingPage = lazy(() => import('./LandingPage'));

export const routes: AppRoute[] = [
  { path: '/', element: <LandingPage />, layout: 'bare', public: true },
];
