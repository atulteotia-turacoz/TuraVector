import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight, BookOpen, LogIn, Search, MessageSquareText, ShieldCheck, Upload, UserCheck, UserPlus,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { PlanCard, type Plan } from '@/features/plans/shared';
import { ThemePicker } from '@/components/ThemePicker';
import './landing.css';

const FEATURES = [
  { icon: <Upload size={18} />, title: 'Content Review', text: 'Upload manuscripts and documents, keep every version, and follow each one from draft to approval.' },
  { icon: <MessageSquareText size={18} />, title: 'Review & annotation', text: 'Reviewers comment directly on the document. Every annotation is saved with its author and time.' },
  { icon: <UserCheck size={18} />, title: 'Reviewer workflow', text: 'Assign reviewers with due dates, send documents for review or revision, and mark them complete.' },
  { icon: <BookOpen size={18} />, title: 'Reference library', text: 'Store references and ZIP bundles, link them to document versions, and preview them in place.' },
  { icon: <Search size={18} />, title: 'Journal selection', text: 'Find the right journal or conference for your manuscript and keep a shortlist of saved journals.' },
  { icon: <ShieldCheck size={18} />, title: 'Role-based access', text: 'Roles and permissions decide who can upload, review, manage users or see reports.' },
];

const STEPS = [
  { n: '01', title: 'Upload', text: 'An author uploads a document and its references.' },
  { n: '02', title: 'Review', text: 'Assigned reviewers annotate it and send it back for revision or approve it.' },
  { n: '03', title: 'Approve', text: 'The approved version is locked, with its full history kept.' },
];

export default function LandingPage() {
  const { user, loading } = useAuth();
  const primary = user
    ? <Link to="/home" className="btn btn-primary btn-lg">Go to dashboard <ArrowRight size={16} /></Link>
    : <>
      <Link to="/signup/" className="btn btn-primary btn-lg"><UserPlus size={16} /> Create an account</Link>
      <Link to="/login/" className="btn btn-secondary btn-lg"><LogIn size={16} /> Login</Link>
    </>;

  return (
    <div className="ld">
      <header className="ld-top">
        <div className="ld-wrap ld-top-inner">
          <Link to="/" className="logo ld-logo">Tura<span className="logo-mark">Vector</span></Link>
          <nav className="ld-nav" aria-label="Sections">
            <a href="#features" className="hide-sm">Features</a>
            <a href="#workflow" className="hide-sm">How it works</a>
            <a href="#plans">Plans</a>
          </nav>
          <div className="row">
            <ThemePicker />
            {!loading && (user
              ? <Link to="/home" className="btn btn-secondary btn-sm">Dashboard</Link>
              : <>
                <Link to="/login/" className="btn btn-secondary btn-sm"><LogIn size={14} /> Login</Link>
                <Link to="/signup/" className="btn btn-primary btn-sm"><UserPlus size={14} /> Sign up</Link>
              </>)}
          </div>
        </div>
      </header>

      <main>
        <section className="ld-hero">
          <div className="ld-wrap">
            <div className="eyebrow">Document management for research teams</div>
            <h1 className="ld-title">Write, review and approve documents in one place.</h1>
            <p className="ld-lede">
              TuraVector keeps your manuscripts, reviews, references and journal choices together, with a clear record
              of who changed what and when.
            </p>
            <div className="row wrap ld-cta">
              {!loading && primary}
              <a href="#features" className="btn btn-secondary btn-lg">See what it does</a>
            </div>
            {user && <p className="small muted ld-signed">Signed in as {user.full_name}.</p>}
          </div>
        </section>

        <section id="features" className="ld-section">
          <div className="ld-wrap">
            <div className="section-title">Features</div>
            <h2 className="ld-h2">Everything a document goes through</h2>
            <div className="ld-grid">
              {FEATURES.map((f) => (
                <article key={f.title} className="ld-card">
                  <div className="ld-icon">{f.icon}</div>
                  <h3>{f.title}</h3>
                  <p className="muted">{f.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="workflow" className="ld-section ld-section-well">
          <div className="ld-wrap">
            <div className="section-title">How it works</div>
            <h2 className="ld-h2">From first draft to approved version</h2>
            <ol className="ld-steps">
              {STEPS.map((s) => (
                <li key={s.n}>
                  <span className="ld-step-n">{s.n}</span>
                  <h3>{s.title}</h3>
                  <p className="muted">{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <PlansSection signedIn={!!user} />

        <section className="ld-section">
          <div className="ld-wrap ld-final">
            <h2 className="ld-h2">{user ? 'Pick up where you left off.' : 'Ready to get started?'}</h2>
            <p className="muted">{user ? 'Your documents and tools are on your dashboard.' : 'Create an account for yourself or your university in a minute.'}</p>
            <div className="ld-cta">{!loading && primary}</div>
          </div>
        </section>
      </main>

      <footer className="ld-foot">
        <div className="ld-wrap between wrap">
          <span>© {new Date().getFullYear()} TuraVector</span>
          <span className="row">
            <Link to="/documents/terms-and-conditions/">Terms &amp; Conditions</Link>
            <Link to="/documents/privacy-policy/">Privacy Policy</Link>
          </span>
        </div>
      </footer>
    </div>
  );
}

type Audience = 'individual' | 'organisation';
const AUDIENCES: { value: Audience; label: string }[] = [
  { value: 'individual', label: 'For individuals' },
  { value: 'organisation', label: 'For universities & organisations' },
];

/** Public pricing: the active plans set up in the admin, split by who they're offered to. */
function PlansSection({ signedIn }: { signedIn: boolean }) {
  const q = useQuery({
    queryKey: ['subscriptions', 'catalogue'],
    queryFn: async () => (await api.get<{ plans: Plan[] }>('/api/subscriptions/catalogue')).data,
  });
  const [audience, setAudience] = useState<Audience>('individual');
  const plans = q.data?.plans ?? [];
  const offered = AUDIENCES.filter((a) => plans.some((p) => p.audience === 'all' || p.audience === a.value));
  const current = offered.some((a) => a.value === audience) ? audience : offered[0]?.value ?? 'individual';
  const shown = plans.filter((p) => p.audience === 'all' || p.audience === current);

  const action = (p: Plan) => {
    if (signedIn) return <Link to="/plans/" className="btn btn-secondary">Choose plan</Link>;
    if (current === 'organisation') return <Link to={`/signup/?type=organisation&plan=${p.id}`} className={`btn ${p.is_featured ? 'btn-primary' : 'btn-secondary'}`}>Register your institution</Link>;
    return <Link to={`/signup/?plan=${p.id}`} className={`btn ${p.is_featured ? 'btn-primary' : 'btn-secondary'}`}>
      {p.price > 0 && p.trial_days > 0 ? 'Start free trial' : p.price > 0 ? 'Get started' : 'Sign up free'}</Link>;
  };

  return (
    <section id="plans" className="ld-section">
      <div className="ld-wrap">
        <div className="section-title">Plans</div>
        <h2 className="ld-h2">Pay only for the tools you use</h2>
        {q.isLoading ? <p className="muted">Loading plans…</p> : plans.length === 0 ? (
          <p className="muted">Plans and pricing will be published here soon.</p>
        ) : <>
          {offered.length > 1 && (
            <div className="ld-tabs" role="tablist">
              {offered.map((a) => (
                <button key={a.value} type="button" role="tab" aria-selected={current === a.value}
                  className={current === a.value ? 'is-on' : ''} onClick={() => setAudience(a.value)}>{a.label}</button>
              ))}
            </div>
          )}
          <div className="pl-grid">
            {shown.map((p) => <PlanCard key={p.id} plan={p} action={action(p)} />)}
          </div>
          {current === 'organisation' && !signedIn && (
            <p className="small muted ld-plans-note">Choose a plan when you register your university or organisation. It starts once the registration is approved, and every member gets its tools.</p>
          )}
        </>}
      </div>
    </section>
  );
}
