import { lazy, useEffect, type ReactNode } from 'react';
import type { AppRoute } from '@/routes';

const ProjectsListPage = lazy(() => import('./pages/ProjectsListPage'));
const ProjectFormPage = lazy(() => import('./pages/ProjectFormPage'));
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'));
const ProjectDeletePage = lazy(() => import('./pages/ProjectDeletePage'));
const ProjectTimelinePage = lazy(() => import('./pages/ProjectTimelinePage'));
const CollaboratorsListPage = lazy(() => import('./pages/CollaboratorsListPage'));
const AllCollaboratorsPage = lazy(() => import('./pages/AllCollaboratorsPage'));
const ProjectCollaboratorsPage = lazy(() => import('./pages/ProjectCollaboratorsPage'));
const CollaboratorFormPage = lazy(() => import('./pages/CollaboratorFormPage'));
const CollaboratorDeletePage = lazy(() => import('./pages/CollaboratorDeletePage'));
const TaskFormPage = lazy(() => import('./pages/TaskFormPage'));
const TaskDeletePage = lazy(() => import('./pages/TaskDeletePage'));
const UploadDocumentPage = lazy(() => import('./pages/UploadDocumentPage'));
const VersionCollaboratorsPage = lazy(() => import('./pages/VersionCollaboratorsPage'));

/** Sets the browser tab title like the Django `{% block title %}`. */
function Titled({ title, children }: { title: string; children: ReactNode }) {
  useEffect(() => { document.title = title; }, [title]);
  return <>{children}</>;
}
const t = (title: string, el: ReactNode) => <Titled title={title}>{el}</Titled>;
const P = '/journal-selector/projects/:projectId';

// projects/*.html extend other_documents_base.html -> 'other'; version_collaborators.html extends base.html -> 'main'
export const routes: AppRoute[] = [
  { path: '/journal-selector/projects/', element: t('Projects - TuraVector', <ProjectsListPage />), layout: 'other' },
  { path: '/journal-selector/projects/create/', element: t('Create New Project - TuraVector', <ProjectFormPage key="create" />), layout: 'other' },
  { path: `${P}/`, element: t('Project - TuraVector', <ProjectDetailPage />), layout: 'other' },
  { path: `${P}/edit/`, element: t('Edit Project - TuraVector', <ProjectFormPage key="edit" />), layout: 'other' },
  { path: `${P}/delete/`, element: t('Delete Project - TuraVector', <ProjectDeletePage />), layout: 'other' },
  { path: `${P}/timeline/`, element: t('Timeline - TuraVector', <ProjectTimelinePage />), layout: 'other' },
  { path: '/journal-selector/collaborators/', element: t('Project Collaborators - TuraVector', <CollaboratorsListPage />), layout: 'other' },
  { path: '/journal-selector/all-collaborators-projects/', element: t('Project Collaborators - TuraVector', <AllCollaboratorsPage />), layout: 'other' },
  { path: `${P}/collaborators/`, element: t('Collaborators - TuraVector', <ProjectCollaboratorsPage />), layout: 'other' },
  { path: `${P}/collaborators/add/`, element: t('Add Collaborator - TuraVector', <CollaboratorFormPage key="add" />), layout: 'other' },
  { path: `${P}/collaborators/:collaboratorId/edit/`, element: t('Edit Collaborator - TuraVector', <CollaboratorFormPage key="edit" />), layout: 'other' },
  { path: `${P}/collaborators/:collaboratorId/delete/`, element: t('Remove Collaborator - TuraVector', <CollaboratorDeletePage />), layout: 'other' },
  { path: `${P}/tasks/add/`, element: t('Add Task - TuraVector', <TaskFormPage key="add" />), layout: 'other' },
  { path: `${P}/tasks/:taskId/edit/`, element: t('Edit Task - TuraVector', <TaskFormPage key="edit" />), layout: 'other' },
  { path: `${P}/tasks/:taskId/delete/`, element: t('Delete Task - TuraVector', <TaskDeletePage />), layout: 'other' },
  { path: `${P}/upload-document/`, element: t('Upload Document - TuraVector', <UploadDocumentPage />), layout: 'other' },
  { path: '/content-lab-management/version/:versionId/collaborators/', element: t('Manage Version Collaborators - TuraVector', <VersionCollaboratorsPage />), layout: 'main' },
];
