import { useEffect, useRef, useState } from 'react';
import { Monitor, Moon, Palette, Sun } from 'lucide-react';
import { ACCENTS, useTheme, type ThemeMode } from '@/lib/theme';

/** Light / dark / system switch plus the accent palette — mirrors the reference app's picker. */
export function ThemePicker() {
  const { mode, setMode, accent, setAccent, customHex, resolved } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const modes: { value: ThemeMode; label: string; icon: JSX.Element }[] = [
    { value: 'light', label: 'Light', icon: <Sun size={14} /> },
    { value: 'dark', label: 'Dark', icon: <Moon size={14} /> },
    { value: 'system', label: 'System', icon: <Monitor size={14} /> },
  ];
  return (
    <div className="pop-wrap" ref={ref}>
      <button className="btn btn-ghost btn-icon" aria-label="Theme and colour" title="Theme and colour" onClick={() => setOpen((o) => !o)}>
        {resolved === 'dark' ? <Moon size={16} /> : <Palette size={16} />}
      </button>
      {open && (
        <div className="pop theme-pop">
          <div className="pop-head">Appearance</div>
          <div className="filter-tabs" style={{ margin: '2px 9px 8px' }}>
            {modes.map((m) => (
              <button key={m.value} className={`filter-tab row-tight ${mode === m.value ? 'active' : ''}`} onClick={() => setMode(m.value)}>{m.icon}{m.label}</button>
            ))}
          </div>
          <div className="pop-sep" />
          <div className="pop-head">Colour palette</div>
          <div className="swatches">
            {ACCENTS.map((a) => (
              <button key={a.name} className={`swatch ${accent === a.name ? 'is-active' : ''}`} title={`${a.label} — ${a.note}`} aria-label={a.label} onClick={() => setAccent(a.name)}>
                <span style={{ background: a.swatch }} />
              </button>
            ))}
          </div>
          <label className="pop-item" style={{ cursor: 'pointer' }}>
            <input type="color" value={customHex || '#9E2B25'} onChange={(e) => setAccent('custom', e.target.value)} style={{ width: 22, height: 22, border: 0, padding: 0, background: 'none' }} />
            <span>Custom colour{accent === 'custom' && customHex ? ` · ${customHex}` : ''}</span>
          </label>
        </div>
      )}
    </div>
  );
}
