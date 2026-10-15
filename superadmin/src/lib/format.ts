/** Date/size formatting. Backend sends ISO-8601 UTC ("...Z"); we render in the user's timezone. */

let userTimeZone: string | undefined;
export function setUserTimeZone(tz?: string | null) {
  userTimeZone = tz && tz !== 'UTC' ? tz : undefined;
}

function toDate(v: string | number | Date | null | undefined): Date | null {
  if (v === null || v === undefined || v === '') return null;
  const d = v instanceof Date ? v : new Date(v);
  return isNaN(d.getTime()) ? null : d;
}

/** "Jan 05, 2025 02:30 PM" — matches Django's `date:"M d, Y h:i A"` used across templates. */
export function formatDateTime(v: string | number | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return '—';
  return d.toLocaleString('en-US', {
    timeZone: userTimeZone, month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true,
  }).replace(',', '').replace(/, (\d{2}:\d{2})/, ' $1');
}

/** "Jan 05, 2025" */
export function formatDate(v: string | number | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return '—';
  return d.toLocaleDateString('en-US', { timeZone: userTimeZone, month: 'short', day: '2-digit', year: 'numeric' });
}

export function timeAgo(v: string | number | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return '';
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return 'Just now';
  if (s < 3600) { const m = Math.floor(s / 60); return `${m} minute${m !== 1 ? 's' : ''} ago`; }
  if (s < 86400) { const h = Math.floor(s / 3600); return `${h} hour${h !== 1 ? 's' : ''} ago`; }
  const days = Math.floor(s / 86400);
  if (days < 7) return `${days} day${days !== 1 ? 's' : ''} ago`;
  return formatDate(d);
}

export function fileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let n = bytes / 1024; let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(1)} ${units[i]}`;
}

export function initials(name: string | null | undefined): string {
  return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join('');
}
