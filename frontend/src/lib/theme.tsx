import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type ThemeMode = 'light' | 'dark' | 'system';

export const ACCENTS = [
  { name: 'mark', label: 'Proof red', swatch: '#9E2B25', note: "The editor's red pen" },
  { name: 'indigo', label: 'Indigo', swatch: '#3B4B8C', note: 'Calm and corporate' },
  { name: 'teal', label: 'Teal', swatch: '#1F6F6B', note: 'Cool and clinical' },
  { name: 'moss', label: 'Moss', swatch: '#3D6B4F', note: 'Quiet green' },
  { name: 'amber', label: 'Amber', swatch: '#8A5A16', note: 'Warm ochre' },
  { name: 'plum', label: 'Plum', swatch: '#6B3A6B', note: 'Deep violet' },
  { name: 'slate', label: 'Slate', swatch: '#3F4A55', note: 'Neutral blue-grey' },
  { name: 'ink', label: 'Ink', swatch: '#1C1B1A', note: 'Monochrome' },
] as const;

const THEME_KEY = 'tura.theme';
const ACCENT_KEY = 'tura.accent';
const CUSTOM_KEY = 'tura.accent.custom';

interface ThemeValue {
  mode: ThemeMode;
  accent: string;
  customHex: string | null;
  resolved: 'light' | 'dark';
  setMode: (m: ThemeMode) => void;
  setAccent: (name: string, hex?: string) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string | null) {
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* storage unavailable */ }
}
const systemPrefersDark = () => typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches;

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => (read(THEME_KEY) as ThemeMode) || 'system');
  const [accent, setAccentState] = useState<string>(() => read(ACCENT_KEY) || 'mark');
  const [customHex, setCustomHex] = useState<string | null>(() => read(CUSTOM_KEY));
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  useEffect(() => {
    if (typeof matchMedia !== 'function') return;
    const mq = matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const resolved: 'light' | 'dark' = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode;

  useEffect(() => {
    const root = document.documentElement;
    if (mode === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', mode);
    root.setAttribute('data-accent', accent);
    if (accent === 'custom' && customHex) root.style.setProperty('--accent-custom', customHex);
    else root.style.removeProperty('--accent-custom');
  }, [mode, accent, customHex]);

  const setMode = useCallback((next: ThemeMode) => { setModeState(next); write(THEME_KEY, next); }, []);
  const setAccent = useCallback((next: string, hex?: string) => {
    setAccentState(next);
    write(ACCENT_KEY, next);
    if (next === 'custom') { setCustomHex(hex ?? null); write(CUSTOM_KEY, hex ?? null); }
  }, []);
  const toggle = useCallback(() => setMode(resolved === 'dark' ? 'light' : 'dark'), [resolved, setMode]);

  const value = useMemo(() => ({ mode, accent, customHex, resolved, setMode, setAccent, toggle }),
    [mode, accent, customHex, resolved, setMode, setAccent, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
