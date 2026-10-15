import axios, { AxiosError } from 'axios';

/** Base URL of the FastAPI backend. Empty = same origin (Vite proxies /api and /media in dev). */
// the backend's address without /api (every call already starts with /api/…); a trailing /api is dropped
export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, '').replace(/\/api$/, '') || '';

const TOKEN_KEY = 'tura.token';

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token: string | null) {
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

export const api = axios.create({ baseURL: API_URL });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !String(error.config?.url || '').includes('/api/auth/login')) {
      setToken(null);
      if (!location.pathname.startsWith('/login')) {
        location.href = `/login/?next=${encodeURIComponent(location.pathname + location.search)}`;
      }
    }
    return Promise.reject(error);
  },
);

/** Human-readable message from an API error (FastAPI `detail`, a string, or validation list). */
export function errorMessage(err: unknown, fallback = 'Something went wrong'): string {
  const e = err as AxiosError<any>;
  const detail = e?.response?.data?.detail ?? e?.response?.data?.message ?? e?.response?.data?.error;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg || String(d)).join('; ');
  return e?.message || fallback;
}

/** Absolute URL for an API path with the auth token appended — for <a href>, <iframe>, WebViewer, downloads. */
export function authUrl(path: string): string {
  const token = getToken();
  const base = path.startsWith('http') ? path : `${API_URL}${path}`;
  if (!token) return base;
  return `${base}${base.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
}

/** Download a file from an authenticated endpoint, honouring Content-Disposition. */
export async function downloadFile(path: string, params?: Record<string, unknown>, fallbackName = 'download') {
  const res = await api.get(path, { params, responseType: 'blob' });
  const cd: string = res.headers['content-disposition'] || '';
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Build multipart FormData from a plain object (skips undefined/null; arrays become repeated keys). */
export function toFormData(values: Record<string, unknown>): FormData {
  const fd = new FormData();
  Object.entries(values).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    if (Array.isArray(v)) v.forEach((item) => fd.append(k, item instanceof Blob ? item : String(item)));
    else if (v instanceof Blob) fd.append(k, v);
    else if (typeof v === 'boolean') fd.append(k, v ? 'true' : 'false');
    else fd.append(k, String(v));
  });
  return fd;
}

/** The superadmin console (User Management, Permissions, Mail, Categories live there). */
export const SUPERADMIN_URL: string =
  (import.meta.env.VITE_SUPERADMIN_URL as string | undefined)?.replace(/\/$/, '') || 'http://localhost:5174';
