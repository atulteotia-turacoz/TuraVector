/** Viewer module: API types and small hooks shared by the viewer pages. */
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import type { AxiosError } from 'axios';
import { api, authUrl, errorMessage } from '@/lib/api';
import { useToast } from '@/components/ui';

export interface ClientConfig {
  PDFTRON_ENABLED: boolean;
  PDFTRON_LICENSE_KEY: string;
  PDFTRON_VERSION: string;
  PDFTRON_PATH: string;
  PDFTRON_LICENSED: boolean;
  ALLOW_DOCUMENT_DOWNLOAD: boolean;
  DOCUMENT_WATERMARK: boolean;
  DOCUMENT_PRINT_DISABLED: boolean;
  ENABLE_ONLYOFFICE_EDITOR: boolean;
  ONLYOFFICE_DOCUMENT_SERVER_URL: string;
  MEDIA_URL: string;
  TIME_ZONE: string;
}

export interface ViewerUser {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  user_type: string;
  user_type_display: string;
  is_manager: boolean;
}

export interface ViewerDocument {
  id: number;
  document_name: string;
  document_number: string;
  stage_status: number;
  stage_status_display: string;
  document_type: string | null;
  brand: string | null;
  country: string | null;
  user: ViewerUser;
  created_at: string | null;
  updated_at: string | null;
}

export interface ViewerVersion {
  id: number;
  document_id: number;
  version_number: string;
  version_count: number;
  file_name: string;
  file_extension: string;
  file_title_name: string;
  stage_status: number;
  stage_status_display: string;
  user_id: number;
  created_at: string | null;
  updated_at: string | null;
  has_file: boolean;
  file_exists: boolean;
  file_size: number | null;
  file_path: string;
  media_url: string | null;
  file_api: string;
}

export interface ViewerReference {
  id: number;
  reference_number: string;
  document_name: string;
  type: string;
  type_display: string;
  subtype: string;
  subtype_display: string;
  therapeutic_area: string | null;
  country: string | null;
  ref_year: number | null;
  file_extension: string;
  file_title_name: string;
  file_name: string;
  has_file: boolean;
  media_url: string | null;
  file_api: string;
  file_exists?: boolean;
  user_id?: number;
  created_by?: ViewerUser | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ReferenceLink {
  id: number;
  reference: ViewerReference;
  linked_by: ViewerUser | null;
  linked_at: string | null;
  notes: string | null;
}

/** GET /api/config (PDFTron licence/path, download/print/watermark flags). */
export function useClientConfig() {
  return useQuery({
    queryKey: ['client-config'],
    queryFn: async () => (await api.get<ClientConfig>('/api/config')).data,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Load a page-context endpoint. When the backend answers like a Django
 * `messages.error(...) + redirect(...)` ({detail, redirect}), show the message and navigate there.
 */
export function usePageData<T>(key: unknown[], url: string | null, params?: Record<string, unknown>) {
  const navigate = useNavigate();
  const toast = useToast();
  const query = useQuery<T, AxiosError<any>>({
    queryKey: ['viewer', ...key],
    queryFn: async () => (await api.get<T>(url as string, { params })).data,
    enabled: !!url,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const redirect = (query.error?.response?.data as any)?.redirect as string | undefined;
  useEffect(() => {
    if (!query.error || !redirect) return;
    const level = (query.error.response?.data as any)?.level;
    const msg = errorMessage(query.error);
    if (level === 'warning') toast.warning(msg); else toast.error(msg);
    navigate(redirect, { replace: true });
  }, [query.error, redirect, navigate, toast]);
  return query;
}

/** Absolute, token-carrying URL of a viewer file endpoint. */
export function fileUrl(apiPath: string, download = false): string {
  return authUrl(download ? `${apiPath}?download=1` : apiPath);
}

/** Django template `{% if value in 'a,b,c' %}` — Python substring containment. */
export function inCsv(value: string | null | undefined, csv: string): boolean {
  return csv.includes(value ?? '');
}

export const WEBVIEWER_EXTENSIONS = 'pdf,doc,docx,xls,xlsx,ppt,pptx';

/** `{% if user.first_name or user.last_name %}{{ first }} {{ last }}{% else %}{{ username }}{% endif %}` */
export function templateUserName(u: { first_name: string; last_name: string; username: string }): string {
  return u.first_name || u.last_name ? `${u.first_name} ${u.last_name}` : u.username;
}

/** user.get_full_name|default:user.username */
export function fullNameOrUsername(u: { first_name: string; last_name: string; username: string }): string {
  return `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username;
}
