/**
 * Helpers shared by the users-module pages.
 *
 * Django views flashed `messages` and redirected. The API answers writes with
 * `{ messages: [{level, text}] }` and refuses with an HTTP error whose `detail` is
 * either a string, a list of strings, or `{ message, redirect }` (permission redirects).
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, type UseQueryOptions } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { api } from '@/lib/api';
import { useToast, Badge } from '@/components/ui';

export interface FlashMessage { level: 'success' | 'info' | 'warning' | 'error'; text: string }
export interface ActionResult { success: boolean; message?: string | null; messages?: FlashMessage[]; [k: string]: unknown }

export interface ApiErrorInfo { status?: number; messages: string[]; redirect?: string; fieldErrors?: Record<string, string[]> }

export function apiError(err: unknown): ApiErrorInfo {
  const e = err as AxiosError<any>;
  const status = e?.response?.status;
  const detail = e?.response?.data?.detail ?? e?.response?.data?.error ?? e?.response?.data?.message;
  if (typeof detail === 'string') return { status, messages: [detail] };
  if (Array.isArray(detail)) return { status, messages: detail.map((d: any) => (typeof d === 'string' ? d : d?.msg || String(d))) };
  if (detail && typeof detail === 'object') {
    return { status, messages: detail.message ? [String(detail.message)] : [], redirect: detail.redirect, fieldErrors: detail.field_errors };
  }
  return { status, messages: [e?.message || 'Something went wrong'] };
}

/** Show a list of Django-style messages as toasts. */
export function useFlash() {
  const toast = useToast();
  return (messages?: FlashMessage[] | null, fallback?: string | null) => {
    const list = messages && messages.length ? messages : fallback ? [{ level: 'success' as const, text: fallback }] : [];
    list.forEach((m) => {
      if (m.level === 'error') toast.error(m.text);
      else if (m.level === 'warning') toast.warning(m.text);
      else if (m.level === 'info') toast.info(m.text);
      else toast.success(m.text);
    });
  };
}

/** Toast every message of an API error. */
export function useErrorToast() {
  const toast = useToast();
  return (err: unknown) => apiError(err).messages.forEach((m) => toast.error(m));
}

/**
 * GET a page's data. A refusal carrying a redirect target behaves like the Django view:
 * flash the error and go to the target page.
 */
export function usePageData<T>(key: unknown[], url: string, params?: Record<string, unknown>,
  options?: Partial<UseQueryOptions<T>>) {
  const navigate = useNavigate();
  const toast = useToast();
  const q = useQuery<T>({
    queryKey: ['users', ...key],
    queryFn: async () => (await api.get<T>(url, { params })).data,
    retry: false,
    ...(options as object),
  });
  useEffect(() => {
    if (!q.error) return;
    const info = apiError(q.error);
    if (info.redirect) {
      info.messages.forEach((m) => toast.error(m));
      navigate(info.redirect, { replace: true });
    }
  }, [q.error]); // eslint-disable-line react-hooks/exhaustive-deps
  return q;
}

export function ActiveBadge({ active }: { active: boolean }) {
  return active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Inactive</Badge>;
}

/** Status labels for document.stage_status / latest version status as used by these templates. */
export function DocStatus({ status, variant = 'dashboard' }: { status: number; variant?: 'dashboard' | 'short' }) {
  if (status === 0) return <Badge>Draft</Badge>;
  if (status === 1) return <Badge tone="warn">{variant === 'dashboard' ? 'Under Review' : 'Review'}</Badge>;
  if (status === 2) return <Badge tone="ok">Approved</Badge>;
  if (status === 3) return <Badge tone="danger">Needs Revision</Badge>;
  return null;
}

/** Django `truncatechars` (counts the ellipsis). */
export function truncate(s: string | null | undefined, n: number): string {
  if (!s) return '';
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/** Django time format "H:i". */
export function timeHM(v: string | null | undefined): string {
  if (!v) return '';
  const d = new Date(v);
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
}

export interface UserRow {
  id: number; username: string; email: string; first_name: string; last_name: string; full_name: string;
  phone: string | null; address: string | null; user_type: string; user_type_new_id: number | null;
  user_type_display: string; is_manager: boolean; is_active: boolean; is_superuser: boolean; is_staff: boolean;
  date_joined: string | null; last_login: string | null; document_count: number | null;
}

export interface PermissionItem {
  id: number; name: string; dashboard: string; module: string; action: string; description: string; is_active: boolean;
  dashboard_display: string; module_display: string; action_display: string; label: string;
}
export interface PermissionGroup { dashboard: string; modules: { module: string; permissions: PermissionItem[] }[] }

export interface RoleItem {
  id: number; name: string; description: string; is_system_role: boolean; is_active: boolean;
  created_at: string | null; updated_at: string | null;
}

export interface UserTypeItem {
  id: number; name: string; code: string; description: string; is_active: boolean; is_system: boolean;
  created_at: string | null; updated_at: string | null; user_count: number | null;
}
