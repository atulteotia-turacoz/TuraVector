/**
 * Rich-text editor with a Word-like ribbon: undo/redo, paragraph style, font, size, bold/italic/underline/
 * strikethrough, sub/superscript, text colour and highlight, alignment, lists, indent, quote, code, link,
 * image, table, horizontal line, clear formatting, find & replace, full screen and a word count.
 * The value is HTML; the server turns it into a .docx keeping that formatting.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  AlignCenter, AlignJustify, AlignLeft, AlignRight, Bold, ChevronDown, Code, Eraser, Highlighter, ImagePlus, IndentDecrease,
  IndentIncrease, Italic, Link2, Link2Off, List, ListOrdered, Maximize2, Minimize2, Minus, Palette, Quote, Redo2,
  Replace, Strikethrough, Subscript, Superscript, Table, Underline, Undo2,
} from 'lucide-react';

const FONTS = [
  'Default', 'Arial', 'Arial Black', 'Arial Narrow', 'Book Antiqua', 'Bookman Old Style', 'Calibri', 'Calibri Light', 'Cambria',
  'Cambria Math', 'Candara', 'Century Gothic', 'Comic Sans MS', 'Consolas', 'Constantia', 'Corbel', 'Courier New',
  'Franklin Gothic Medium', 'Garamond', 'Georgia', 'Gill Sans MT', 'Helvetica', 'Impact', 'Lucida Console',
  'Lucida Sans Unicode', 'Palatino Linotype', 'Rockwell', 'Segoe UI', 'Symbol', 'Tahoma', 'Times New Roman',
  'Trebuchet MS', 'Verdana',
];
const SIZES = [8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40, 48, 60, 72];
const BLOCKS = [{ v: 'p', l: 'Normal text' }, { v: 'h1', l: 'Heading 1' }, { v: 'h2', l: 'Heading 2' }, { v: 'h3', l: 'Heading 3' },
  { v: 'h4', l: 'Heading 4' }, { v: 'blockquote', l: 'Quote' }, { v: 'pre', l: 'Code block' }];
const MAX_IMAGE_PX = 1600;

/** Downscale a picked image so the document stays small. */
function imageToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, MAX_IMAGE_PX / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * scale);
      c.height = Math.round(img.height * scale);
      c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(file.type === 'image/png' && file.size < 400_000 ? c.toDataURL('image/png') : c.toDataURL('image/jpeg', 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Could not read the image')); };
    img.src = url;
  });
}

function Btn({ title, onRun, active, children }: { title: string; onRun: () => void; active?: boolean; children: ReactNode }) {
  return (
    <button type="button" className={`rte-btn ${active ? 'is-on' : ''}`} title={title} aria-label={title} aria-pressed={active}
      onMouseDown={(e) => { e.preventDefault(); onRun(); }}>{children}</button>
  );
}

export function RichTextEditor({ value, onChange, placeholder, minHeight = 320 }: {
  value: string; onChange: (html: string) => void; placeholder?: string; minHeight?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const saved = useRef<Range | null>(null);
  const [state, setState] = useState<Record<string, boolean>>({});
  const [block, setBlock] = useState('p');
  const [full, setFull] = useState(false);
  const [find, setFind] = useState<{ open: boolean; q: string; r: string; note: string }>({ open: false, q: '', r: '', note: '' });
  const [words, setWords] = useState(0);

  useEffect(() => {
    if (ref.current && ref.current.innerHTML !== value) ref.current.innerHTML = value;
    setWords((ref.current?.innerText.trim().match(/\S+/g) ?? []).length);
  }, [value]);

  const emit = () => {
    onChange(ref.current?.innerHTML ?? '');
    setWords((ref.current?.innerText.trim().match(/\S+/g) ?? []).length);
  };
  const refreshState = () => {
    const q = (c: string) => { try { return document.queryCommandState(c); } catch { return false; } };
    setState({
      bold: q('bold'), italic: q('italic'), underline: q('underline'), strikeThrough: q('strikeThrough'),
      subscript: q('subscript'), superscript: q('superscript'), insertUnorderedList: q('insertUnorderedList'),
      insertOrderedList: q('insertOrderedList'), justifyLeft: q('justifyLeft'), justifyCenter: q('justifyCenter'),
      justifyRight: q('justifyRight'), justifyFull: q('justifyFull'),
    });
    try { setBlock(((document.queryCommandValue('formatBlock') as string) || 'p').toLowerCase().replace(/[<>]/g, '') || 'p'); } catch { /* ignore */ }
    const node = window.getSelection()?.anchorNode;
    const el = node && (node.nodeType === 1 ? node as HTMLElement : node.parentElement);
    if (el && ref.current?.contains(el)) {
      const cs = getComputedStyle(el);
      const fam = cs.fontFamily.split(',')[0].replace(/["']/g, '').trim();
      setFont(FONTS.includes(fam) ? fam : 'Default');
      setSize(String(Math.round(parseFloat(cs.fontSize) * 0.75 * 2) / 2));  // px → pt
    }
  };
  const keepSelection = () => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount && ref.current?.contains(sel.anchorNode)) saved.current = sel.getRangeAt(0).cloneRange();
  };
  const restoreSelection = () => {
    const sel = window.getSelection();
    // still in the editor: leave the caret alone, or the browser forgets a pending "bold off" etc.
    if (document.activeElement === ref.current && sel?.rangeCount && ref.current?.contains(sel.anchorNode)) return;
    ref.current?.focus();
    if (saved.current && sel) { sel.removeAllRanges(); sel.addRange(saved.current); }
  };
  const run = (cmd: string, arg?: string) => {
    restoreSelection();
    document.execCommand('styleWithCSS', false, 'true');
    document.execCommand(cmd, false, arg);
    keepSelection();
    emit();
    refreshState();
  };
  const insertHtml = (html: string) => run('insertHTML', html);
  const [size, setSize] = useState('');
  const [font, setFont] = useState('');
  /** Any point size: the browser only knows sizes 1–7, so mark with 7 and rewrite those spans to the exact size. */
  const applySize = (raw: string) => {
    const pt = Number(raw);
    if (!pt || pt < 1 || pt > 400) return;
    restoreSelection();
    document.execCommand('styleWithCSS', false, 'true');
    document.execCommand('fontSize', false, '7');
    ref.current?.querySelectorAll<HTMLElement>('span[style*="xxx-large"], font[size="7"]').forEach((el) => {
      el.removeAttribute('size');
      el.style.fontSize = `${pt}pt`;
    });
    keepSelection();
    emit();
  };

  const addLink = () => {
    keepSelection();
    const url = window.prompt('Link address (https://…)', 'https://');
    if (url && url !== 'https://') {
      run('createLink', /^(https?:|mailto:)/.test(url) ? url : `https://${url}`);
      window.getSelection()?.collapseToEnd();  // keep typing after the link, not over it
      keepSelection();
    }
  };
  const addTable = () => {
    keepSelection();
    const spec = window.prompt('Table size: rows × columns', '3 x 3');
    const m = spec?.match(/(\d+)\s*[x×*,]\s*(\d+)/i);
    if (!m) return;
    const rows = Math.min(Number(m[1]), 50), cols = Math.min(Number(m[2]), 12);
    const cell = (tag: string) => `<${tag}>&nbsp;</${tag}>`;
    const head = `<tr>${Array.from({ length: cols }, () => cell('th')).join('')}</tr>`;
    const body = Array.from({ length: Math.max(rows - 1, 0) }, () => `<tr>${Array.from({ length: cols }, () => cell('td')).join('')}</tr>`).join('');
    insertHtml(`<table class="rte-table">${head}${body}</table><p><br></p>`);
  };
  const addImage = async (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) { window.alert('Choose an image file (PNG, JPG, GIF).'); return; }
    try { insertHtml(`<img src="${await imageToDataUrl(file)}" alt="" style="max-width: 100%;">`); }
    catch (e) { window.alert((e as Error).message); }
    if (fileRef.current) fileRef.current.value = '';
  };
  const replaceAll = () => {
    if (!ref.current || !find.q) return;
    let count = 0;
    const walker = document.createTreeWalker(ref.current, NodeFilter.SHOW_TEXT);
    const re = new RegExp(find.q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const t = n.nodeValue ?? '';
      const next = t.replace(re, () => { count += 1; return find.r; });
      if (next !== t) n.nodeValue = next;
    }
    setFind((f) => ({ ...f, note: count ? `Replaced ${count}` : 'Not found' }));
    emit();
  };

  return (
    <div className={`rte ${full ? 'rte-full' : ''}`}>
      <div className="rte-bar" role="toolbar" aria-label="Formatting" onMouseDown={keepSelection}>
        <div className="rte-group">
          <Btn title="Undo (Ctrl+Z)" onRun={() => run('undo')}><Undo2 size={15} /></Btn>
          <Btn title="Redo (Ctrl+Y)" onRun={() => run('redo')}><Redo2 size={15} /></Btn>
        </div>
        <div className="rte-group">
          <select className="rte-select" aria-label="Paragraph style" value={BLOCKS.some((b) => b.v === block) ? block : 'p'}
            onMouseDown={keepSelection} onChange={(e) => run('formatBlock', e.target.value)}>
            {BLOCKS.map((b) => <option key={b.v} value={b.v}>{b.l}</option>)}
          </select>
          <Menu label="Font" width={170} current={font || 'Font'} search
            items={FONTS.map((f) => ({ value: f, label: f, style: f === 'Default' ? undefined : { fontFamily: f } }))}
            onPick={(f) => { run('fontName', f === 'Default' ? 'IBM Plex Sans' : f); setFont(f); }} onOpen={keepSelection} />
          <div className="rte-size">
            <input className="rte-select rte-narrow" aria-label="Font size" placeholder="Size" inputMode="decimal"
              value={size} onMouseDown={keepSelection} onFocus={keepSelection}
              onChange={(e) => setSize(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applySize(size); } }} />
            <Menu label="Font sizes" width={70} current="" compact
              items={SIZES.map((s) => ({ value: String(s), label: String(s) }))}
              onPick={(v) => { setSize(v); applySize(v); }} onOpen={keepSelection} />
          </div>
        </div>
        <div className="rte-group">
          <Btn title="Bold (Ctrl+B)" active={state.bold} onRun={() => run('bold')}><Bold size={15} /></Btn>
          <Btn title="Italic (Ctrl+I)" active={state.italic} onRun={() => run('italic')}><Italic size={15} /></Btn>
          <Btn title="Underline (Ctrl+U)" active={state.underline} onRun={() => run('underline')}><Underline size={15} /></Btn>
          <Btn title="Strikethrough" active={state.strikeThrough} onRun={() => run('strikeThrough')}><Strikethrough size={15} /></Btn>
          <Btn title="Subscript" active={state.subscript} onRun={() => run('subscript')}><Subscript size={15} /></Btn>
          <Btn title="Superscript" active={state.superscript} onRun={() => run('superscript')}><Superscript size={15} /></Btn>
          <label className="rte-btn rte-color" title="Text colour" onMouseDown={keepSelection}>
            <Palette size={15} /><input type="color" aria-label="Text colour" defaultValue="#c0392b" onChange={(e) => run('foreColor', e.target.value)} />
          </label>
          <label className="rte-btn rte-color" title="Highlight" onMouseDown={keepSelection}>
            <Highlighter size={15} /><input type="color" aria-label="Highlight colour" defaultValue="#ffff00" onChange={(e) => run('hiliteColor', e.target.value)} />
          </label>
          <Btn title="Clear formatting" onRun={() => { run('removeFormat'); run('formatBlock', 'p'); }}><Eraser size={15} /></Btn>
        </div>
        <div className="rte-group">
          <Btn title="Align left" active={state.justifyLeft} onRun={() => run('justifyLeft')}><AlignLeft size={15} /></Btn>
          <Btn title="Centre" active={state.justifyCenter} onRun={() => run('justifyCenter')}><AlignCenter size={15} /></Btn>
          <Btn title="Align right" active={state.justifyRight} onRun={() => run('justifyRight')}><AlignRight size={15} /></Btn>
          <Btn title="Justify" active={state.justifyFull} onRun={() => run('justifyFull')}><AlignJustify size={15} /></Btn>
        </div>
        <div className="rte-group">
          <Btn title="Bulleted list" active={state.insertUnorderedList} onRun={() => run('insertUnorderedList')}><List size={15} /></Btn>
          <Btn title="Numbered list" active={state.insertOrderedList} onRun={() => run('insertOrderedList')}><ListOrdered size={15} /></Btn>
          <Btn title="Decrease indent" onRun={() => run('outdent')}><IndentDecrease size={15} /></Btn>
          <Btn title="Increase indent" onRun={() => run('indent')}><IndentIncrease size={15} /></Btn>
          <Btn title="Quote" active={block === 'blockquote'} onRun={() => run('formatBlock', block === 'blockquote' ? 'p' : 'blockquote')}><Quote size={15} /></Btn>
          <Btn title="Code block" active={block === 'pre'} onRun={() => run('formatBlock', block === 'pre' ? 'p' : 'pre')}><Code size={15} /></Btn>
        </div>
        <div className="rte-group">
          <Btn title="Insert link" onRun={addLink}><Link2 size={15} /></Btn>
          <Btn title="Remove link" onRun={() => run('unlink')}><Link2Off size={15} /></Btn>
          <Btn title="Insert image" onRun={() => { keepSelection(); fileRef.current?.click(); }}><ImagePlus size={15} /></Btn>
          <Btn title="Insert table" onRun={addTable}><Table size={15} /></Btn>
          <Btn title="Horizontal line" onRun={() => run('insertHorizontalRule')}><Minus size={15} /></Btn>
        </div>
        <div className="rte-group">
          <Btn title="Find and replace" active={find.open} onRun={() => setFind((f) => ({ ...f, open: !f.open, note: '' }))}><Replace size={15} /></Btn>
          <Btn title={full ? 'Exit full screen' : 'Full screen'} onRun={() => setFull((v) => !v)}>{full ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</Btn>
        </div>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => void addImage(e.target.files?.[0])} />
      </div>
      {find.open && (
        <div className="rte-find">
          <input className="input" placeholder="Find" aria-label="Find" value={find.q} onChange={(e) => setFind((f) => ({ ...f, q: e.target.value, note: '' }))} />
          <input className="input" placeholder="Replace with" aria-label="Replace with" value={find.r} onChange={(e) => setFind((f) => ({ ...f, r: e.target.value }))} />
          <button type="button" className="btn btn-secondary btn-sm" disabled={!find.q} onClick={replaceAll}>Replace all</button>
          {find.note && <span className="small muted">{find.note}</span>}
        </div>
      )}
      <div ref={ref} className="rte-body" contentEditable role="textbox" aria-multiline="true" aria-label="Text"
        data-placeholder={placeholder} style={{ minHeight }} suppressContentEditableWarning spellCheck
        onInput={emit} onKeyUp={() => { keepSelection(); refreshState(); }} onMouseUp={() => { keepSelection(); refreshState(); }}
        onBlur={keepSelection} />
      <div className="rte-foot"><span>{words} word{words === 1 ? '' : 's'}</span><span>Saved as a Word document (.docx)</span></div>
    </div>
  );
}

/** A dropdown that scrolls (a native <select> list does not on every browser), optionally searchable.
 *  Picking keeps the editor's selection: items act on mousedown without taking focus. */
function Menu({ label, items, current, onPick, onOpen, width, search, compact }: {
  label: string; items: { value: string; label: string; style?: React.CSSProperties }[]; current: string;
  onPick: (v: string) => void; onOpen: () => void; width: number; search?: boolean; compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [open]);
  const shown = q ? items.filter((i) => i.label.toLowerCase().includes(q.toLowerCase())) : items;
  return (
    <div className="rte-menu" ref={box}>
      <button type="button" className={compact ? 'rte-btn rte-caret' : 'rte-select rte-menu-btn'} style={compact ? undefined : { width }}
        aria-label={label} aria-haspopup="listbox" aria-expanded={open} title={label}
        onMouseDown={(e) => { e.preventDefault(); onOpen(); setOpen((o) => !o); setQ(''); }}>
        {!compact && <span className="truncate">{current}</span>}<ChevronDown size={13} />
      </button>
      {open && (
        <div className="rte-pop" role="listbox" aria-label={label} style={{ minWidth: Math.max(width, compact ? 70 : 190) }}>
          {search && <input className="input rte-pop-search" autoFocus placeholder="Search fonts…" value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && shown[0]) { e.preventDefault(); onPick(shown[0].value); setOpen(false); } }} />}
          <div className="rte-pop-list">
            {shown.map((i) => (
              <button type="button" key={i.value} role="option" aria-selected={i.value === current} className={`rte-pop-item ${i.value === current ? 'is-on' : ''}`}
                style={i.style} onMouseDown={(e) => { e.preventDefault(); onPick(i.value); setOpen(false); }}>{i.label}</button>
            ))}
            {shown.length === 0 && <div className="rte-pop-item faint">No match</div>}
          </div>
        </div>
      )}
    </div>
  );
}

export const htmlIsEmpty = (html: string) => !/<img|<table|<hr/i.test(html) && !html.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim();
