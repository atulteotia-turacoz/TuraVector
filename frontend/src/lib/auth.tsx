import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, getToken, setToken } from './api';

/** Mirrors the `can_*` helpers on the Django User model (see backend app/core/permissions.py). */
export type Capability =
  | 'can_access_dashboard' | 'can_access_manager_dashboard' | 'can_access_reviewer_dashboard'
  | 'can_upload' | 'can_create_upload' | 'can_access_library' | 'can_create_library' | 'can_edit_library'
  | 'can_delete_library' | 'can_manage_users' | 'can_create_users' | 'can_edit_users' | 'can_assign_roles'
  | 'can_manage_roles' | 'can_create_roles' | 'can_edit_roles' | 'can_assign_permissions' | 'can_view_reports'
  | 'can_create_reports' | 'can_manage_email_settings' | 'can_create_email_settings' | 'can_edit_email_settings'
  | 'can_view_mail_logs' | 'can_retry_emails' | 'can_view_documents' | 'can_view_all_documents'
  | 'can_edit_documents' | 'can_edit_all_documents' | 'can_delete_documents' | 'can_delete_all_documents'
  | 'can_delete_document_versions' | 'can_delete_all_document_versions' | 'can_view_document_history'
  | 'can_view_all_document_history' | 'can_create_document_versions' | 'can_upload_documents'
  | 'can_manage_library' | 'can_manage_reference_zip' | 'can_review_documents' | 'can_reject_documents'
  | 'can_assign_reviewers' | 'can_access_other_documents'
  | 'can_search_journals' | 'can_access_reviews' | 'can_view_completed' | 'can_access_archive'
  | 'can_access_references' | 'can_access_document_references' | 'can_access_content_lab_dashboard'
  | 'can_access_other_documents_dashboard' | 'tag_can_manage_users' | 'tag_can_manage_email_settings'
  | 'tag_can_manage_permissions';

export interface Me {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string | null;
  address: string | null;
  timezone: string;
  user_type: string;
  user_type_code: string;
  user_type_display: string;
  user_type_new_id: number | null;
  is_manager: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  is_active: boolean;
  /** user_type == 'manager' or is_manager */
  is_manager_like: boolean;
  /** is_staff or is_superuser or manager */
  is_admin_like: boolean;
  date_joined: string | null;
  last_login: string | null;
  roles: { id: number; name: string }[];
  capabilities: Record<Capability, boolean>;
  /** the user's workspace (null for platform superadmins) */
  organisation: Organisation | null;
  /** admin of a university/organisation workspace */
  is_org_admin: boolean;
  /** a Turacoz user (or superuser) who approves invoices */
  is_invoice_approver?: boolean;
}

export interface Organisation {
  id: number;
  name: string;
  kind: 'university' | 'organisation' | 'individual';
  website: string;
  logo_url: string | null;
  status: 'pending' | 'active' | 'rejected' | 'suspended';
  role: 'admin' | 'member' | null;
  membership_status: 'active' | 'pending' | 'rejected' | null;
}

interface AuthValue {
  user: Me | null;
  loading: boolean;
  login: (username: string, password: string, privacy_consent: boolean) => Promise<Me>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  can: (cap: Capability) => boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getToken());
  const qc = useQueryClient();

  const refresh = useCallback(async () => {
    if (!getToken()) { setUser(null); setLoading(false); return; }
    try {
      const { data } = await api.get<Me>('/api/auth/me');
      setUser(data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const login = useCallback(async (username: string, password: string, privacy_consent: boolean) => {
    const { data } = await api.post('/api/auth/login', { username, password, privacy_consent });
    setToken(data.access_token);
    setUser(data.user);
    return data.user as Me;
  }, []);

  const logout = useCallback(async () => {
    try { await api.post('/api/auth/logout'); } catch { /* token may already be invalid */ }
    setToken(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  const can = useCallback((cap: Capability) => !!user && (user.is_superuser || !!user.capabilities?.[cap]), [user]);

  const value = useMemo(() => ({ user, loading, login, logout, refresh, can }), [user, loading, login, logout, refresh, can]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

/** The authenticated user — only call inside protected routes. */
export function useUser(): Me {
  const { user } = useAuth();
  if (!user) throw new Error('useUser called outside an authenticated route');
  return user;
}
