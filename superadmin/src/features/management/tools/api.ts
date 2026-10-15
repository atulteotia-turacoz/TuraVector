/** Tools module: API types and small helpers. Backend: app/routers/tools_*.py (prefix /api/tools). */

export type CategoryKind = 'document-types' | 'countries' | 'brands' | 'therapeutic-areas';

export interface CategoryMeta {
  kind: CategoryKind;
  /** list title, e.g. "Document Types" */
  plural: string;
  /** form title, e.g. "Document Type" */
  singular: string;
  hasCode: boolean;
  listPath: string;
  bulkPath: string;
  addInfo: string;
  editInfo: string;
}

export const CATEGORY_META: Record<CategoryKind, CategoryMeta> = {
  'document-types': {
    kind: 'document-types', plural: 'Document Types', singular: 'Document Type', hasCode: false,
    listPath: '/documents/categories/document-types/', bulkPath: '/documents/bulk-import/document-types/',
    addInfo: 'Document types help categorize documents by their purpose or format (e.g., Report, Proposal, Manual).',
    editInfo: "Document types help categorize documents by their purpose or format. Inactive types won't appear in selection menus.",
  },
  countries: {
    kind: 'countries', plural: 'Countries', singular: 'Country', hasCode: true,
    listPath: '/documents/categories/countries/', bulkPath: '/documents/bulk-import/countries/',
    addInfo: 'Countries are used to specify geographical regions for document organization and compliance.',
    editInfo: "Countries specify geographical regions for documents. Inactive countries won't be available for selection.",
  },
  brands: {
    kind: 'brands', plural: 'Brands', singular: 'Brand', hasCode: true,
    listPath: '/documents/categories/brands/', bulkPath: '/documents/bulk-import/brands/',
    addInfo: 'Brands help organize documents by product lines or company divisions.',
    editInfo: "Brands organize documents by product lines. Inactive brands won't appear in document creation forms.",
  },
  'therapeutic-areas': {
    kind: 'therapeutic-areas', plural: 'Therapeutic Areas', singular: 'Therapeutic Area', hasCode: false,
    listPath: '/documents/categories/therapeutic-areas/', bulkPath: '/documents/bulk-import/therapeutic-areas/',
    addInfo: 'Therapeutic areas categorize documents by medical or research specialties.',
    editInfo: "Therapeutic areas categorize medical/research documents. Inactive areas won't be selectable.",
  },
};

export interface CategoryItem {
  id: number;
  name: string;
  code_name?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CategoryList {
  page_title: string;
  category_name: string;
  singular: string;
  has_code: boolean;
  search_query: string;
  total_items: number;
  active_count: number;
  inactive_count: number;
  items: CategoryItem[];
  pagination: null | { page: number; num_pages: number; start_index: number; end_index: number; has_pagination: boolean };
}

export interface FlashMessage { level: 'success' | 'error' | 'warning' | 'info'; text: string }

export interface BulkResult {
  import_type: string;
  success_count: number;
  error_count: number;
  errors: string[];
  messages: FlashMessage[];
}

export interface EmailLogRow {
  id: number;
  email_type: string;
  email_type_display: string;
  status: string;
  status_display: string;
  recipient_email: string;
  recipient_user: string | null;
  sender_user: string | null;
  from_email: string;
  subject: string;
  document: { document_number: string; document_name: string } | null;
  document_version: string | null;
  retry_count: number;
  can_retry: boolean;
  sent_at: string | null;
  created_at: string;
  message_content?: string;
  error_message?: string | null;
}

export interface MailLogs {
  items: EmailLogRow[];
  total: number;
  page: number;
  pages: number;
  email_types: { value: string; label: string }[];
  status_choices: { value: string; label: string }[];
  stats: { total: number; sent: number; failed: number; pending: number };
}

export interface SmtpConfig {
  id: number;
  host: string;
  port: number;
  username: string;
  password?: string;
  use_tls: boolean;
  use_ssl: boolean;
  from_email: string;
  from_name: string;
  display_name: string;
  protocol: string;
  mailtype: string;
  charset: string;
  encoding: string;
  crlf: string;
  newline: string;
  wordwrap: boolean;
  test_email: string | null;
  is_active: boolean;
  status: string;
  is_tested: boolean;
  last_tested: string | null;
  test_result: string | null;
  created_at: string;
}

export interface JournalResult {
  id: number;
  name: string;
  publisher: string;
  publishing_model: string;
  impact_factor: string;
  impact_factor_year: number | string;
  downloads: number;
  submission_days: number | string;
  primary_subject: string;
  secondary_subjects: string[];
  is_saved: boolean;
  cover_image_url: string | null;
  source: 'local' | 'springer_api' | 'elsevier_api' | 'pubmed_api';
  submission_url: string;
  website_url: string;
}

export interface JournalSearchResponse {
  journals: JournalResult[];
  count: number;
  query: string;
  warning?: string;
  sources?: { local_count?: number; springer_api_count?: number; elsevier_api_count?: number; pubmed_api_count?: number };
}

export interface SavedJournal {
  id: number;
  manuscript_title: string;
  journal: {
    id: number; name: string; publisher: string | null; publishing_model: string;
    impact_factor: string | null; impact_factor_year: number | null; submission_to_decision_days: number | null;
    cover_image_url: string | null; submission_url: string | null; website_url: string | null;
  };
}

/** Read a theme colour (CSS variable) so charts follow light/dark and every palette. */
export function cssVar(name: string, fallback = '#888'): string {
  if (typeof window === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
