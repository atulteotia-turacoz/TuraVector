/** Plans & tools: shared types, tool icons and the plan card used on sign-up, home and the Plans page. */
import type { ReactNode } from 'react';
import {
  AppWindow, BarChart3, BookOpen, Brain, Check, FileText, FlaskConical, Globe, GraduationCap, Layers,
  MessageSquare, PenTool, Search, Shield, Sparkles, SpellCheck,
} from 'lucide-react';
import './plans.css';

export interface Tool { key: string; name: string; description: string; features: string[]; kind: 'dashboard' | 'app'; icon: string; is_free: boolean }
export interface Plan {
  id: number; name: string; description: string; price: number; currency: string; billing_period: string;
  billing_period_label: string; trial_days: number; audience: string; is_featured: boolean; tax_percent?: number;
  tools: { key: string; name: string }[];
}
export interface Subscription {
  id: number; plan_id: number | null; plan_name: string; tools: { key: string; name: string }[]; price: number;
  currency: string; billing_period: string; billing_period_label: string;
  status: 'pending' | 'active' | 'cancelled'; state: 'pending' | 'active' | 'scheduled' | 'expired' | 'cancelled';
  is_trial: boolean; source: string; starts_at: string | null; ends_at: string | null; paid_at: string | null;
  tax_percent: number; tax_amount: number; total: number; invoice_id: number | null; cancelled_at: string | null;
  can_cancel: boolean; payment_ref: string;
}

const ICONS: Record<string, (size: number) => JSX.Element> = {
  flask: (s) => <FlaskConical size={s} />, 'file-text': (s) => <FileText size={s} />, brain: (s) => <Brain size={s} />,
  'graduation-cap': (s) => <GraduationCap size={s} />, 'spell-check': (s) => <SpellCheck size={s} />,
  'book-open': (s) => <BookOpen size={s} />, 'bar-chart': (s) => <BarChart3 size={s} />, search: (s) => <Search size={s} />,
  'pen-tool': (s) => <PenTool size={s} />, 'message-square': (s) => <MessageSquare size={s} />, layers: (s) => <Layers size={s} />,
  globe: (s) => <Globe size={s} />, shield: (s) => <Shield size={s} />, sparkles: (s) => <Sparkles size={s} />,
};

export function ToolIcon({ icon, size = 22 }: { icon: string; size?: number }) {
  return (ICONS[icon] ?? ((s: number) => <AppWindow size={s} />))(size);
}

export function money(v: number, currency = 'INR') {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: v % 1 ? 2 : 0 }).format(v);
}

export function priceLabel(p: { price: number; currency: string; billing_period: string; billing_period_label: string }) {
  if (p.price <= 0) return 'Free';
  const per = { monthly: '/ month', quarterly: '/ quarter', half_yearly: '/ 6 months', yearly: '/ year', lifetime: 'one-time' }[p.billing_period];
  return `${money(p.price, p.currency)} ${per ?? p.billing_period_label}`;
}

/** What a subscription awaiting payment costs, GST included. */
export function dueLabel(s: { price: number; total: number; tax_amount: number; currency: string }) {
  return s.tax_amount > 0 ? `${money(s.total, s.currency)} (incl. ${money(s.tax_amount, s.currency)} GST)` : money(s.total || s.price, s.currency);
}

/** A selectable / actionable plan card. */
export function PlanCard({ plan, selected, onSelect, action, note }: {
  plan: Plan; selected?: boolean; onSelect?: () => void; action?: ReactNode; note?: ReactNode;
}) {
  const body = (
    <>
      <div className="pl-card-head">
        <h3>{plan.name}</h3>
        {plan.is_featured && <span className="badge badge-accent">Popular</span>}
      </div>
      <div className="pl-price">{priceLabel(plan)}</div>
      {plan.price > 0 && !!plan.tax_percent && <div className="pl-gst">+ {plan.tax_percent}% GST</div>}
      {plan.trial_days > 0 && plan.price > 0 && <div className="pl-trial">{plan.trial_days}-day free trial</div>}
      {plan.description && <p className="pl-desc">{plan.description}</p>}
      <ul className="pl-tools">{plan.tools.map((t) => <li key={t.key}><Check size={13} /> {t.name}</li>)}</ul>
      {note && <div className="pl-note">{note}</div>}
      {action && <div className="pl-action">{action}</div>}
    </>
  );
  if (onSelect) {
    return (
      <label className={`pl-card is-selectable ${selected ? 'is-selected' : ''}`}>
        <input type="radio" name="plan" checked={!!selected} onChange={onSelect} className="pl-radio" />
        {body}
      </label>
    );
  }
  return <div className={`pl-card ${plan.is_featured ? 'is-featured' : ''}`}>{body}</div>;
}

export const STATE_LABEL: Record<Subscription['state'], { label: string; tone: string }> = {
  active: { label: 'Active', tone: 'ok' }, scheduled: { label: 'Starts later', tone: 'accent' },
  pending: { label: 'Awaiting payment', tone: 'warn' }, expired: { label: 'Expired', tone: '' }, cancelled: { label: 'Cancelled', tone: '' },
};

/** Indian states and union territories with their GST state codes. */
export const INDIAN_STATES: [string, string][] = [
  ['35', 'Andaman and Nicobar Islands'], ['37', 'Andhra Pradesh'], ['12', 'Arunachal Pradesh'], ['18', 'Assam'],
  ['10', 'Bihar'], ['04', 'Chandigarh'], ['22', 'Chhattisgarh'], ['26', 'Dadra and Nagar Haveli and Daman and Diu'],
  ['07', 'Delhi'], ['30', 'Goa'], ['24', 'Gujarat'], ['06', 'Haryana'], ['02', 'Himachal Pradesh'],
  ['01', 'Jammu and Kashmir'], ['20', 'Jharkhand'], ['29', 'Karnataka'], ['32', 'Kerala'], ['38', 'Ladakh'],
  ['31', 'Lakshadweep'], ['23', 'Madhya Pradesh'], ['27', 'Maharashtra'], ['14', 'Manipur'], ['17', 'Meghalaya'],
  ['15', 'Mizoram'], ['13', 'Nagaland'], ['21', 'Odisha'], ['34', 'Puducherry'], ['03', 'Punjab'], ['08', 'Rajasthan'],
  ['11', 'Sikkim'], ['33', 'Tamil Nadu'], ['36', 'Telangana'], ['16', 'Tripura'], ['09', 'Uttar Pradesh'],
  ['05', 'Uttarakhand'], ['19', 'West Bengal'],
];
