/** Shared types and helpers for the projects module (port of templates/projects/*). */
import { useEffect, useRef, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, type QueryKey } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { api, errorMessage } from '@/lib/api';
import { Badge, ErrorNotice, Loading, useToast } from '@/components/ui';
import './projects.css';

export interface Choice { value: string; label: string }
export interface UserOption { value: number; label: string }

export interface UserBrief {
  id: number; username: string; email: string; first_name: string; last_name: string; full_name: string; initials: string;
}

export interface ProjectSummary {
  id: number; title: string; description: string; description_short: string;
  status: string; status_display: string; priority: string; priority_display: string;
  project_type: string; project_type_other: string | null; project_type_display: string;
  client_type: string; client_other: string | null; client_type_display: string;
  client_poc_name: string | null; client_poc_email: string | null; has_authors: boolean; journal_name: string | null;
  therapeutic_area: string; therapeutic_area_other: string | null; therapeutic_area_display: string;
  sub_therapy_area: string | null; start_date: string | null; estimated_end_date: string | null;
  actual_end_date: string | null; deadline: string | null; research_field: string; keywords: string;
  budget: string | null; owner: UserBrief; is_owner: boolean; collaborator_count: number;
  created_at: string; updated_at: string;
}

export interface Author { id?: number | null; name: string; affiliation: string; email: string; author_type: string; author_type_display?: string; DELETE?: boolean }

export interface Task {
  id: number; title: string; description: string; description_short: string; status: string; status_display: string;
  priority: string; priority_display: string; assigned_to: UserBrief | null; assigned_to_id: number | null;
  due_date: string | null; created_at: string;
}

export interface Collaborator {
  id: number; role: string; role_display: string; joined_at: string; user: UserBrief; project_id: number;
}

export interface ProjectDocument {
  id: number; title: string; description: string; description_short: string; file: string; file_name: string;
  uploaded_by: UserBrief; uploaded_at: string; can_delete: boolean;
}

export interface ProjectDetail extends ProjectSummary {
  tasks: Task[]; documents: ProjectDocument[]; collaborators: Collaborator[]; authors: Author[];
  keywords_list: string[]; progress_percentage: number; is_collaborator: boolean;
}

/** Django `|date:"M d, Y"` for a DateField (no timezone shift). */
export function fmtDay(value: string | null | undefined, fallback = ''): string {
  if (!value) return fallback;
  const [y, m, d] = value.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return fallback;
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
}

/** Django `|title` */
export function titleCase(s: string): string {
  return s.replace(/\w\S*/g, (w) => w[0]!.toUpperCase() + w.slice(1).toLowerCase());
}

const STATUS_TONES: Record<string, 'accent' | 'ok' | 'warn' | 'danger' | undefined> = {
  planning: undefined, active: 'accent', on_hold: 'warn', completed: 'ok', cancelled: 'danger',
  todo: undefined, in_progress: 'accent', not_started: undefined, delayed: 'danger',
  low: undefined, medium: 'accent', high: 'warn', urgent: 'danger',
};
export function StatusBadge({ value, label }: { value: string; label: ReactNode }) {
  return <Badge tone={STATUS_TONES[value]}>{label}</Badge>;
}

export function Avatar({ text }: { text: string }) {
  return <span className="avatar">{text || '?'}</span>;
}

/** Parsed `detail` of a 400 from a Django-form-like endpoint. */
export interface FormErrorDetail { message: string; errors: Record<string, string[]>; non_field_errors: string[] }
export function formError(err: unknown): FormErrorDetail | null {
  const d = (err as AxiosError<any>)?.response?.data?.detail;
  if (d && typeof d === 'object' && !Array.isArray(d) && 'errors' in d) return d as FormErrorDetail;
  return null;
}

/** "Please correct the following errors:" box used by add/edit collaborator & task templates. */
export function ErrorList({ detail, title = 'Please correct the following errors:' }: { detail: FormErrorDetail | null; title?: string }) {
  if (!detail) return null;
  const all = [...detail.non_field_errors, ...Object.values(detail.errors).flat()];
  if (!all.length) return null;
  return (
    <div className="notice notice-danger">
      <div className="notice-title">{title}</div>
      {all.map((e, i) => <div key={i}>{e}</div>)}
    </div>
  );
}

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

export const ROLE_DESCRIPTIONS = (
  <div className="well small proj-help">
    <div className="notice-title">Role Descriptions:</div>
    <ul>
      <li><strong>Co-Investigator:</strong> Can view, edit, and manage project content</li>
      <li><strong>Researcher:</strong> Can view and contribute to project research</li>
      <li><strong>Analyst:</strong> Can analyze data and provide insights</li>
      <li><strong>Contributor:</strong> Can view project and add content</li>
      <li><strong>Reviewer:</strong> Can view and review project milestones</li>
    </ul>
  </div>
);

export const PRIORITY_LEVELS = (
  <div className="well small proj-help">
    <div className="notice-title">Priority Levels:</div>
    <ul>
      <li><strong>Low:</strong> Nice to have, no rush</li>
      <li><strong>Medium:</strong> Standard priority task</li>
      <li><strong>High:</strong> Important, should be completed soon</li>
      <li><strong>Urgent:</strong> Critical, needs immediate attention</li>
    </ul>
  </div>
);
