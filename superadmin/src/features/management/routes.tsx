/**
 * Management sections moved here from the user app: User Management, Permissions Management,
 * Mail (logs + SMTP settings) and Manage Categories (+ user types). The pages and the API calls
 * are the same ones the user app used, so behaviour is unchanged; only the location moved.
 * Paths keep the original URLs, so the user app can redirect old links straight here.
 */
import { lazy, type ReactNode } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import './users/users.css';
import './tools/tools.css';

const ManageUsers = lazy(() => import('./users/pages/ManageUsers'));
const CreateUser = lazy(() => import('./users/pages/CreateUser'));
const BulkImportUsers = lazy(() => import('./users/pages/BulkImport'));
const UserProfile = lazy(() => import('./users/pages/UserProfile'));
const EditUser = lazy(() => import('./users/pages/EditUser'));
const ChangePassword = lazy(() => import('./users/pages/ChangePassword'));
const ViewPassword = lazy(() => import('./users/pages/ViewPassword'));
const UserPermissions = lazy(() => import('./users/pages/UserPermissions'));
const RolesManagement = lazy(() => import('./users/pages/RolesManagement'));
const RoleCreate = lazy(() => import('./users/pages/RoleEditor').then((m) => ({ default: m.RoleCreate })));
const RoleEditLegacy = lazy(() => import('./users/pages/RoleEditor').then((m) => ({ default: () => <m.RoleEdit variant="legacy" /> })));
const RoleEditComp = lazy(() => import('./users/pages/RoleEditor').then((m) => ({ default: () => <m.RoleEdit variant="comprehensive" /> })));
const PermissionDashboard = lazy(() => import('./users/pages/Comprehensive').then((m) => ({ default: m.PermissionDashboard })));
const CompRoles = lazy(() => import('./users/pages/Comprehensive').then((m) => ({ default: m.CompRoles })));
const CompRoleDetail = lazy(() => import('./users/pages/Comprehensive').then((m) => ({ default: m.CompRoleDetail })));
const CompRoleCreate = lazy(() => import('./users/pages/Comprehensive').then((m) => ({ default: m.CompRoleCreate })));
const CompUserRoles = lazy(() => import('./users/pages/Comprehensive').then((m) => ({ default: m.CompUserRoles })));
const CompUserPermissions = lazy(() => import('./users/pages/Comprehensive').then((m) => ({ default: m.CompUserPermissions })));
const DashboardAccess = lazy(() => import('./users/pages/Comprehensive').then((m) => ({ default: m.DashboardAccess })));
const UserTypesList = lazy(() => import('./users/pages/UserTypes').then((m) => ({ default: m.UserTypesList })));
const UserTypeCreate = lazy(() => import('./users/pages/UserTypes').then((m) => ({ default: m.UserTypeCreate })));
const UserTypeEdit = lazy(() => import('./users/pages/UserTypes').then((m) => ({ default: m.UserTypeEdit })));

const CategoryListPage = lazy(() => import('./tools/CategoryListPage'));
const CategoryFormPage = lazy(() => import('./tools/CategoryFormPage'));
const BulkImportPage = lazy(() => import('./tools/BulkImportPage'));
const CountryUploadPage = lazy(() => import('./tools/CountryUploadPage'));
const MailLogsPage = lazy(() => import('./tools/MailLogsPage'));
const EmailLogDetailPage = lazy(() => import('./tools/EmailLogDetailPage'));
const SmtpSettingsPage = lazy(() => import('./tools/SmtpSettingsPage'));
const SmtpFormPage = lazy(() => import('./tools/SmtpFormPage'));
const StatusUpdatePage = lazy(() => import('./doccore/StatusUpdatePage'));

function DocToAdmin() {
  const { documentId } = useParams();
  return <Navigate to={`/documents/document/${documentId}/change/`} replace />;
}

const KINDS = ['document-types', 'countries', 'brands', 'therapeutic-areas'] as const;

export const managementRoutes: { path: string; element: ReactNode }[] = [
  // User Management
  { path: '/library/manage-users/', element: <ManageUsers /> },
  { path: '/library/create-user/', element: <CreateUser /> },
  { path: '/library/bulk-import-users/', element: <BulkImportUsers /> },
  { path: '/library/user/:userId/view/', element: <UserProfile /> },
  { path: '/library/user/:userId/edit/', element: <EditUser /> },
  { path: '/library/user/:userId/change-password/', element: <ChangePassword /> },
  { path: '/library/user/:userId/view-password/', element: <ViewPassword /> },
  { path: '/library/user/:userId/permissions/', element: <UserPermissions /> },
  // Permissions Management
  { path: '/library/roles/', element: <RolesManagement /> },
  { path: '/library/role/create/', element: <RoleCreate /> },
  { path: '/library/role/:roleId/edit/', element: <RoleEditLegacy /> },
  { path: '/library/permissions/dashboard/', element: <PermissionDashboard /> },
  { path: '/library/permissions/roles/', element: <CompRoles /> },
  { path: '/library/permissions/roles/create/', element: <CompRoleCreate /> },
  { path: '/library/permissions/roles/:roleId/', element: <CompRoleDetail /> },
  { path: '/library/permissions/roles/:roleId/edit/', element: <RoleEditComp /> },
  { path: '/library/permissions/users/:userId/roles/', element: <CompUserRoles /> },
  { path: '/library/permissions/users/:userId/permissions/', element: <CompUserPermissions /> },
  { path: '/library/permissions/dashboard-access/', element: <DashboardAccess /> },
  // Manage Categories
  ...KINDS.flatMap((k) => [
    { path: `/documents/categories/${k}/`, element: <CategoryListPage kind={k} key={`l-${k}`} /> },
    { path: `/documents/categories/${k}/add/`, element: <CategoryFormPage kind={k} key={`a-${k}`} /> },
    { path: `/documents/categories/${k}/edit/:itemId/`, element: <CategoryFormPage kind={k} key={`e-${k}`} /> },
    { path: `/documents/bulk-import/${k}/`, element: <BulkImportPage kind={k} key={`b-${k}`} /> },
  ]),
  { path: '/documents/categories/countries/upload/', element: <CountryUploadPage /> },
  { path: '/library/user-types/', element: <UserTypesList /> },
  { path: '/library/user-type/create/', element: <UserTypeCreate /> },
  { path: '/library/user-type/:userTypeId/edit/', element: <UserTypeEdit /> },
  // Mail
  { path: '/documents/mail-logs/', element: <MailLogsPage /> },
  { path: '/documents/mail-logs/:emailLogId/', element: <EmailLogDetailPage /> },
  { path: '/documents/smtp-settings/', element: <SmtpSettingsPage /> },
  { path: '/documents/smtp-settings/add/', element: <SmtpFormPage /> },
  { path: '/documents/smtp-settings/edit/:smtpId/', element: <SmtpFormPage /> },
  // Document / version status updates (staff-only; notifies the owner, same API as before)
  { path: '/documents/document/:documentId/update-status/', element: <StatusUpdatePage kind="document" /> },
  { path: '/documents/version/:versionId/update-status/', element: <StatusUpdatePage kind="version" /> },
  // After saving, the API points at the user-app document page; in the admin open the document record
  { path: '/documents/document/:documentId/', element: <DocToAdmin /> },
  // "no permission" redirects from the API point at user-app dashboards; in the admin go home
  ...['/library/manager-dashboard/', '/library/reports/', '/documents/home/', '/documents/content-lab/', '/documents/manager-dashboard/']
    .map((path) => ({ path, element: <Navigate to="/" replace /> })),
];
