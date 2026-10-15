/** Types and helpers for the /api/superadmin endpoints. */
import { useQuery } from '@tanstack/react-query';
import { api } from './api';

export const API = '/api/superadmin';

export interface LinkInfo { app: string; model: string; pk?: string }

export interface ModelEntry {
  label: string; name: string; object_name: string; app: string; model: string;
  perms: { add: boolean; change: boolean; delete: boolean }; count: number | null;
  /** workspace = rows of the chosen workspace's members; platform = global */
  scope: 'workspace' | 'platform';
}
export interface AppEntry { app_label: string; name: string; models: ModelEntry[] }

export interface LogEntry {
  id: number; action_time: string; action_flag: number; is_addition: boolean; is_change: boolean; is_deletion: boolean;
  object_id: string | null; object_repr: string; content_type: string | null; change_message: string;
  link: LinkInfo | null; user: { id: number; username: string | null; full_name: string };
}

export interface Cell {
  text?: string; kind?: 'bool' | 'datetime' | 'date' | 'file' | 'link'; bool?: boolean | null; value?: string;
  link?: LinkInfo; url?: string | null; href?: string; route?: string;
}

export type FieldKind =
  | 'char' | 'email' | 'url' | 'ip' | 'text' | 'int' | 'float' | 'decimal' | 'bool' | 'nullbool' | 'date' | 'datetime'
  | 'json' | 'fk' | 'm2m' | 'file' | 'image' | 'uuid' | 'choice' | 'computed' | 'password_hash' | 'password' | 'usable_password';

export interface FieldMeta {
  name: string; label: string; kind: FieldKind; readonly: boolean; required: boolean; help_text?: string;
  max_length?: number | null; choices?: [string | number | null, string][];
  rel?: { label: string; verbose_name: string; registered: boolean; app?: string; model?: string };
  widget?: 'autocomplete' | 'filter_horizontal' | 'select'; allowed_extensions?: string[];
}

export interface Fieldset { name: string | null; fields: string[]; classes: string[]; description?: string | null }

export interface InlineMeta {
  label: string; verbose_name: string; verbose_name_plural: string; style: 'tabular' | 'stacked'; fk: string; extra: number;
  fields: FieldMeta[];
}

export interface FormLayout { fieldsets: Fieldset[]; fields: Record<string, FieldMeta>; inlines: InlineMeta[]; view_only: boolean }

export interface ModelConfig {
  label: string; app: string; app_name: string; model: string; object_name: string;
  verbose_name: string; verbose_name_plural: string; perms: { add: boolean; change: boolean; delete: boolean };
  list_display: Column[]; list_filter: string[]; list_editable: string[]; editable_fields: Record<string, FieldMeta>;
  search_fields: string[]; date_hierarchy: string | null; actions: { name: string; description: string }[];
  add_form: FormLayout; change_form: FormLayout; extra_links: { route: string; label: string }[];
}

export interface Column { index: number; name: string; label: string; sortable: boolean; editable: boolean }
export interface FilterChoice { label: string; params: Record<string, string>; selected?: boolean }
export interface FilterSpec { title: string; path: string; keys: string[]; choices: FilterChoice[] }
export interface DateHierarchy {
  field: string; title: string; keys: string[]; back: FilterChoice | null; choices: FilterChoice[];
}

export interface ChangeList {
  label: string; verbose_name: string; verbose_name_plural: string; columns: Column[];
  ordering: { index: number; desc: boolean }[];
  rows: { pk: string; str: string; cells: Cell[]; values: Record<string, any> }[];
  count: number; full_count: number; page: number; pages: number; per_page: number; can_show_all: boolean; show_all: boolean;
  filters: FilterSpec[]; date_hierarchy: DateHierarchy | null; search_enabled: boolean; q: string;
  actions: { name: string; description: string }[];
}

export interface DeleteNode { model: string; str: string; link?: LinkInfo; children: DeleteNode[] }
export interface DeleteSummary {
  objects: DeleteNode[]; counts: { model: string; count: number }[]; protected: { model: string; str: string; link?: LinkInfo }[];
  truncated: boolean; verbose_name: string; verbose_name_plural: string;
}

export interface Message { level: 'success' | 'info' | 'warning' | 'error'; message: string }

export function adminPath(l: LinkInfo, suffix: 'change' | 'delete' | 'history' | '' = 'change'): string {
  if (!l.pk) return `/${l.app}/${l.model}/`;
  return `/${l.app}/${l.model}/${encodeURIComponent(l.pk)}/${suffix ? `${suffix}/` : ''}`;
}

/**
 * Models that are not listed under their app group in the sidebar / app index:
 * - documents.SMTPSettings lives in the "Settings" section of the sidebar instead;
 * - authentication.SMTPConfig is a legacy table that no code reads (email uses SMTPSettings);
 * - auth.Group ("Authentication and Authorization") is Django's unused groups table.
 * Their pages still work by URL; nothing is removed from the database.
 */
export const HIDDEN_FROM_GROUPS = new Set(['documents.SMTPSettings', 'authentication.SMTPConfig', 'auth.Group']);
export const SMTP_SETTINGS_PATH = '/documents/smtpsettings/';

export function useIndex() {
  return useQuery({
    queryKey: ['admin', 'index'],
    queryFn: async () => (await api.get<{ apps: AppEntry[]; recent_actions: LogEntry[] }>(`${API}/index`)).data,
    select: (d) => ({
      ...d,
      apps: d.apps
        .map((a) => ({ ...a, models: a.models.filter((m) => !HIDDEN_FROM_GROUPS.has(m.label)) }))
        .filter((a) => a.models.length > 0),
    }),
  });
}

export function useModelConfig(app: string, model: string) {
  return useQuery({
    queryKey: ['admin', 'config', app, model],
    queryFn: async () => (await api.get<ModelConfig>(`${API}/models/${app}/${model}/config`)).data,
    staleTime: 5 * 60_000,
  });
}

/** Pull Django-style form errors out of an API error. */
export interface FormErrorPayload {
  message?: string; errors?: Record<string, string[]>; non_field_errors?: string[];
  inline_errors?: Record<string, Record<string, Record<string, string[]>>>; row_errors?: Record<string, Record<string, string[]>>;
  protected?: DeleteSummary['protected'];
}
export function formErrors(err: unknown): FormErrorPayload | null {
  const d = (err as any)?.response?.data?.detail;
  return d && typeof d === 'object' && !Array.isArray(d) ? (d as FormErrorPayload) : null;
}
