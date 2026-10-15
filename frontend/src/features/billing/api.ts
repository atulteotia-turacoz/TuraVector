/** Invoices: university admins use /api/org/invoices, Turacoz approvers /api/billing/invoices. */
export interface InvoiceRow {
  id: number; number: string; organisation_id: number; organisation: string; cycle: string; cycle_label: string;
  status: InvoiceStatus; status_label: string; total: number; currency: string; period_start: string | null;
  period_end: string | null; created_at: string | null; paid_at: string | null;
}
export type InvoiceStatus = 'pending_turacoz' | 'pending_client' | 'awaiting_payment' | 'paid' | 'rejected';
export interface InvoiceLine {
  id: number; description: string; sac_code: string; unit: string; unit_label: string; quantity: number; rate: number;
  amount: number; tax_percent: number; cgst: number; sgst: number; igst: number;
}
export interface Invoice extends InvoiceRow {
  tax_mode: 'intra' | 'inter' | 'overseas'; tax_mode_label: string; subtotal: number; cgst: number; sgst: number;
  igst: number; amount_in_words: string; seller: Record<string, string>; buyer: Record<string, string>;
  turacoz_remarks: string; client_remarks: string; turacoz_approved_by: string | null; turacoz_approved_at: string | null;
  client_approved_by: string | null; client_approved_at: string | null; payment_id: string;
  lines: InvoiceLine[];
  requests: { id: number; requested_by: string; created_at: string | null; document_id: number | null; document: string | null;
    document_number: string | null; requirement: string }[];
  events: { action: string; note: string; by: string; at: string | null }[];
}

export const inr = (v: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(v || 0);

export const STATUS_TONE: Record<InvoiceStatus, 'ok' | 'warn' | 'danger' | 'accent' | undefined> = {
  pending_turacoz: 'warn', pending_client: 'accent', awaiting_payment: 'warn', paid: 'ok', rejected: 'danger',
};

export const EVENT_LABELS: Record<string, string> = {
  created: 'Invoice generated', adjusted: 'Quantities or rates adjusted by Turacoz', turacoz_approved: 'Approved by Turacoz',
  cancelled: 'Cancelled by Turacoz', client_approved: 'Approved by the university', client_query: 'Sent back with a query',
  paid: 'Payment received',
};

export const invoiceBase = (approver: boolean) => (approver ? '/api/billing/invoices' : '/api/org/invoices');
