import { lazy, useEffect, type ReactNode } from 'react';
import type { AppRoute } from '@/routes';

const LoginPage = lazy(() => import('./LoginPage'));
const SignupPage = lazy(() => import('./SignupPage'));
const LogoutPage = lazy(() => import('./LogoutPage'));
const ProfilePage = lazy(() => import('./ProfilePage'));
const OtherDocumentsProfilePage = lazy(() => import('./OtherDocumentsProfilePage'));
const DashboardSelectionPage = lazy(() => import('./DashboardSelectionPage'));
const NotificationsPage = lazy(() => import('./NotificationsPage'));
const HelpSupportPage = lazy(() => import('./HelpSupportPage'));
const TermsPage = lazy(() => import('./LegalPages').then((m) => ({ default: m.TermsPage })));
const PrivacyPolicyPage = lazy(() => import('./LegalPages').then((m) => ({ default: m.PrivacyPolicyPage })));

/** Sets the browser tab title like the Django `{% block title %}`. */
function Titled({ title, children }: { title: string; children: ReactNode }) {
  useEffect(() => { document.title = title; }, [title]);
  return <>{children}</>;
}

const t = (title: string, el: ReactNode) => <Titled title={title}>{el}</Titled>;

const login = t('Login - TuraVector', <LoginPage />);
const signup = t('Sign Up - TuraVector', <SignupPage />);
const profile = t('Profile - TuraVector', <ProfilePage />);
const selection = t('TuraVector - Select Dashboard', <DashboardSelectionPage />);

// authentication.urls was mounted both at '/' and at '/auth/' in Django — keep both.
export const routes: AppRoute[] = [
  { path: '/login/', element: login, layout: 'bare', public: true },
  { path: '/signup/', element: signup, layout: 'bare', public: true },
  { path: '/logout/', element: <LogoutPage />, layout: 'bare', public: true },
  { path: '/profile/', element: profile, layout: 'main' },
  { path: '/auth/', element: login, layout: 'bare', public: true },
  { path: '/auth/login/', element: login, layout: 'bare', public: true },
  { path: '/auth/signup/', element: signup, layout: 'bare', public: true },
  { path: '/auth/logout/', element: <LogoutPage />, layout: 'bare', public: true },
  { path: '/auth/profile/', element: profile, layout: 'main' },

  { path: '/home', element: selection, layout: 'bare' },
  { path: '/content-lab-management/notifications/', element: t('Notifications - TuraVector', <NotificationsPage />), layout: 'main' },
  { path: '/content-lab-management/help-support/', element: t('Help & Support - TuraVector', <HelpSupportPage />), layout: 'main' },
  { path: '/journal-selector/profile/', element: t('Profile - Other Documents - TuraVector', <OtherDocumentsProfilePage />), layout: 'other' },
  { path: '/documents/terms-and-conditions/', element: t('Terms and Conditions - TuraVector', <TermsPage />), layout: 'bare', public: true },
  { path: '/documents/privacy-policy/', element: t('Privacy Policy - TuraVector', <PrivacyPolicyPage />), layout: 'bare', public: true },
];
