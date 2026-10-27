/** Helpers for the version-sharing pages: page payload loading with Django-style 403 redirects. */
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, type QueryKey } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { api, errorMessage } from '@/lib/api';
import { ErrorNotice, Loading, useToast } from '@/components/ui';
import './sharing.css';

export interface Choice { value: string; label: string }

/**
 * GET a page payload. On 403 behave like the Django view: flash the message and redirect.
 */
export function usePageData<T>(key: QueryKey, url: string, redirectTo: string | ((err: AxiosError<any>) => string), params?: Record<string, unknown>, enabled = true) {
  const navigate = useNavigate();
  const toast = useToast();
  const handled = useRef(false);
  const q = useQuery({
    queryKey: [...key, params ?? {}],
    queryFn: async () => (await api.get<T>(url, { params })).data,
    retry: false,
    enabled,
  });
  useEffect(() => {
    const err = q.error as AxiosError | null;
    if (err?.response?.status === 403 && !handled.current) {
      handled.current = true;
      toast.error(errorMessage(err));
      navigate(typeof redirectTo === 'function' ? redirectTo(err as AxiosError<any>) : redirectTo, { replace: true });
    }
  }, [q.error, navigate, toast, redirectTo]);
  return q;
}

export function PageState({ q }: { q: { isLoading: boolean; error: unknown } }) {
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  return null;
}
