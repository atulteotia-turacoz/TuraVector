import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { api, errorMessage } from '@/lib/api';
import { useToast } from '@/components/ui';

/** Backend answers Django's `messages.error + redirect` with {detail, redirect}. */
export interface DenyBody { detail?: string; redirect?: string | null; error?: string }

export function redirectOf(err: unknown): string | null | undefined {
  return (err as AxiosError<DenyBody>)?.response?.data?.redirect;
}

/**
 * Query a library page endpoint. When the backend denies access with a redirect target
 * (Django's messages.error + redirect), show the message and navigate there.
 */
export function useLibraryPage<T>(key: unknown[], url: string, params?: Record<string, unknown>): UseQueryResult<T> {
  const navigate = useNavigate();
  const toast = useToast();
  const q = useQuery<T>({
    queryKey: ['library', ...key, params ?? {}],
    queryFn: async () => (await api.get<T>(url, { params })).data,
    retry: false,
  });
  useEffect(() => {
    if (!q.error) return;
    const target = redirectOf(q.error);
    if (target) {
      toast.error(errorMessage(q.error));
      navigate(target, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.error]);
  return q;
}

/** Handle a write-action result/error the way the Django redirect + flash message did. */
export function useActionFeedback() {
  const navigate = useNavigate();
  const toast = useToast();
  return {
    success(data: { message?: string; redirect?: string | null }, fallbackRedirect?: string) {
      if (data.message) toast.success(data.message);
      const to = data.redirect ?? fallbackRedirect;
      if (to) navigate(to);
    },
    failure(err: unknown) {
      toast.error(errorMessage(err));
      const to = redirectOf(err);
      if (to && to !== window.location.pathname) navigate(to);
    },
  };
}

// ----------------------------------------------------------------- shapes
export interface Named { id: number; name: string }

export interface LibraryDocument {
  id: number;
  document_number: string;
  document_name: string;
  created_by_is_owner: boolean;
  created_by_name: string;
  document_type: string | null;
  brand: { id: number; name: string; code_name: string } | null;
  country: { id: number; name: string; code_name: string } | null;
  therapeutic_area: string | null;
  stage_status: number;
  version_count: number;
  first_version_number: string | null;
  owner_id: number;
  owner_name: string;
  owner_user_type: string;
  created_at: string;
  updated_at: string;
  modified_by_first_name: string | null;
}

export interface LibraryResponse {
  documents: LibraryDocument[];
  brands: Named[];
  countries: Named[];
  document_types: Named[];
  therapeutic_areas: Named[];
  stats: { total_documents: number; draft_documents: number; review_documents: number; approved_documents: number; revised_documents: number };
  selected: Record<'search' | 'document_type' | 'brand' | 'country' | 'status', string>;
  is_manager_or_teacher: boolean;
}

export interface ReferenceRow {
  id: number;
  reference_number: string;
  document_name: string;
  type: string;
  type_display: string;
  subtype: string;
  subtype_display: string;
  therapeutic_area: string | null;
  ref_year: number | null;
  has_file: boolean;
  user_id: number;
}

export interface ReferenceDetail extends ReferenceRow {
  country: string | null;
  ref_number: string | null;
  file_name: string;
  file_extension: string;
  file_title_name: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  owner_username: string | null;
}

export interface ZipDetail {
  id: number;
  reference_zip_number: string;
  file_title_name: string;
  file_extension: string;
  has_file: boolean;
  file_size: number | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  modified_by: string;
  owner: string;
  document: { id: number; document_name: string; document_number: string; document_type: string | null; stage_status: number; stage_status_display: string };
  version: { id: number; version_number: string };
}

/** Labels used by library.html / assign_reviewer.html for stage_status. */
export const STAGE_BADGE: Record<number, { label: string; tone?: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  0: { label: 'Draft', tone: 'muted' },
  1: { label: 'Under Review', tone: 'warn' },
  2: { label: 'Approved', tone: 'ok' },
  3: { label: 'Needs Revision', tone: 'danger' },
};

/** Django `filesizeformat`. */
export function filesizeformat(bytes: number): string {
  const KB = 1024, MB = KB * 1024, GB = MB * 1024;
  const fmt = (n: number) => n.toFixed(1);
  if (bytes < KB) return `${bytes} byte${bytes === 1 ? '' : 's'}`;
  if (bytes < MB) return `${fmt(bytes / KB)} KB`;
  if (bytes < GB) return `${fmt(bytes / MB)} MB`;
  return `${fmt(bytes / GB)} GB`;
}

/** The time part ("02:30 PM") of a timestamp in the user's timezone. */
export function timePart(formatted: string): string {
  const parts = formatted.split(' ');
  return parts.length > 3 ? parts.slice(3).join(' ') : '';
}
