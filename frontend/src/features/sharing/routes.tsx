import { lazy, useEffect, type ReactNode } from 'react';
import type { AppRoute } from '@/routes';

const VersionCollaboratorsPage = lazy(() => import('./pages/VersionCollaboratorsPage'));

/** Sets the browser tab title like the Django `{% block title %}`. */
function Titled({ title, children }: { title: string; children: ReactNode }) {
  useEffect(() => { document.title = title; }, [title]);
  return <>{children}</>;
}
const t = (title: string, el: ReactNode) => <Titled title={title}>{el}</Titled>;
// version_collaborators.html extends base.html -> 'main'
export const routes: AppRoute[] = [
  { path: '/content-lab-management/version/:versionId/collaborators/', element: t('Manage Version Collaborators - TuraVector', <VersionCollaboratorsPage />), layout: 'main' },
];
