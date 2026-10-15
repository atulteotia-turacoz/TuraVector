import { useEffect } from 'react';
import type { AxiosError } from 'axios';
import { api } from '@/lib/api';

/** Message of a Django-style `{error: ...}` response, or null for network errors. */
export function apiError(err: unknown): string | null {
  const e = err as AxiosError<any>;
  if (!e?.response) return null;
  const d = e.response.data;
  const msg = d?.error ?? d?.detail ?? d?.message;
  if (typeof msg === 'string') return msg;
  if (Array.isArray(msg)) return msg.map((x: any) => x.msg || String(x)).join('; ');
  return 'Unknown error occurred';
}

/** Django `timesince` (two adjacent units, e.g. "2 days, 3 hours"). */
export function timesince(value: string | null | undefined): string {
  if (!value) return '';
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return '';
  let since = Math.floor((Date.now() - then) / 1000);
  if (since <= 0) return '0 minutes';
  const chunks: [number, string][] = [
    [60 * 60 * 24 * 365, 'year'], [60 * 60 * 24 * 30, 'month'], [60 * 60 * 24 * 7, 'week'],
    [60 * 60 * 24, 'day'], [60 * 60, 'hour'], [60, 'minute'],
  ];
  const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? '' : 's'}`;
  let i = chunks.findIndex(([secs]) => Math.floor(since / secs) !== 0);
  if (i === -1) return '0 minutes';
  const parts: string[] = [];
  for (let depth = 0; depth < 2 && i < chunks.length; depth++, i++) {
    const [secs, unit] = chunks[i]!;
    const count = Math.floor(since / secs);
    if (count === 0) break;
    parts.push(plural(count, unit));
    since -= count * secs;
  }
  return parts.join(', ');
}

/** Django `truncatewords:N` */
export function truncatewords(value: string, n: number): string {
  const words = (value || '').split(/\s+/).filter(Boolean);
  if (words.length <= n) return words.join(' ');
  return `${words.slice(0, n).join(' ')} …`;
}

/** Effective display timezone (same rule as lib/format: 'UTC' / empty = browser local). */
export function displayTz(tz?: string | null): string | undefined {
  return tz && tz !== 'UTC' ? tz : undefined;
}

/** Django `date:"M d, Y H:i"` */
export function formatDateTime24(value: string | null | undefined, tz?: string | null): string {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: displayTz(tz), month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  return `${get('month')} ${get('day')}, ${get('year')} ${get('hour')}:${get('minute')}`;
}

/**
 * Port of static/js/timezone_detection.js, which base.html loaded on every page:
 * detects the browser timezone, keeps it in sessionStorage('userTimezone') and posts it
 * to the set-timezone API once per browser (localStorage 'lastSentTimezone').
 */
function sendTimezoneToServer(timezone: string) {
  let last: string | null = null;
  try { last = localStorage.getItem('lastSentTimezone'); } catch { /* ignore */ }
  if (last === timezone) return;
  api.post('/api/auth/set-timezone', { timezone })
    .then(() => { try { localStorage.setItem('lastSentTimezone', timezone); } catch { /* ignore */ } })
    .catch(() => { /* Django only logged a warning */ });
}

const OFFSET_MAP: Record<string, string> = {
  '-330': 'Asia/Kolkata', '-300': 'Asia/Karachi', '-360': 'Asia/Dhaka', '-480': 'Asia/Shanghai', '-540': 'Asia/Tokyo',
  '0': 'UTC', '60': 'Europe/London', '120': 'Europe/Paris', '300': 'America/New_York', '360': 'America/Chicago',
  '420': 'America/Denver', '480': 'America/Los_Angeles',
};

export function detectAndSetTimezone() {
  try {
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (detected) {
      try { sessionStorage.setItem('userTimezone', detected); } catch { /* ignore */ }
      sendTimezoneToServer(detected);
    }
  } catch {
    const guessed = OFFSET_MAP[String(new Date().getTimezoneOffset())] || 'UTC';
    try { sessionStorage.setItem('userTimezone', guessed); } catch { /* ignore */ }
    sendTimezoneToServer(guessed);
  }
}

export function useTimezoneAutoDetect() {
  useEffect(() => {
    detectAndSetTimezone();
    const id = window.setInterval(() => {
      let stored: string | null = null;
      try { stored = sessionStorage.getItem('userTimezone'); } catch { /* ignore */ }
      if (Intl.DateTimeFormat().resolvedOptions().timeZone !== stored) detectAndSetTimezone();
    }, 60000);
    return () => window.clearInterval(id);
  }, []);
}

/** Only follow same-site relative `next` targets. */
export function safeNext(next: string | null): string | null {
  if (!next || !next.startsWith('/') || next.startsWith('//')) return null;
  return next;
}
