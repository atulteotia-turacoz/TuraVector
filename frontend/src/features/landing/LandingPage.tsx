import { Link } from 'react-router-dom';
import {
  ArrowRight, BookOpen, FolderKanban, LogIn, MessageSquareText, ShieldCheck, Upload, UserCheck,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { ThemePicker } from '@/components/ThemePicker';
import './landing.css';

const FEATURES = [
  { icon: <Upload size={18} />, title: 'Content Lab', text: 'Upload manuscripts and documents, keep every version, and follow each one from draft to approval.' },
  { icon: <MessageSquareText size={18} />, title: 'Review & annotation', text: 'Reviewers comment directly on the document. Every annotation is saved with its author and time.' },
  { icon: <UserCheck size={18} />, title: 'Reviewer workflow', text: 'Assign reviewers with due dates, send documents for review or revision, and mark them complete.' },
  { icon: <BookOpen size={18} />, title: 'Reference library', text: 'Store references and ZIP bundles, link them to document versions, and preview them in place.' },
  { icon: <FolderKanban size={18} />, title: 'Research projects', text: 'Plan projects with milestones, tasks and collaborators, and find the right journal or conference.' },
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
    : <Link to="/login/" className="btn btn-primary btn-lg"><LogIn size={16} /> Login</Link>;

  return (
    <div className="ld">
      <header className="ld-top">
        <div className="ld-wrap ld-top-inner">
          <Link to="/" className="logo ld-logo">Tura<span className="logo-mark">Vector</span></Link>
          <nav className="ld-nav hide-sm" aria-label="Sections">
            <a href="#features">Features</a>
            <a href="#workflow">How it works</a>
          </nav>
          <div className="row">
            <ThemePicker />
            {!loading && (user
              ? <Link to="/home" className="btn btn-secondary btn-sm">Dashboard</Link>
              : <Link to="/login/" className="btn btn-primary btn-sm"><LogIn size={14} /> Login</Link>)}
          </div>
        </div>
      </header>

      <main>
        <section className="ld-hero">
          <div className="ld-wrap">
            <div className="eyebrow">Document management for research teams</div>
            <h1 className="ld-title">Write, review and approve documents in one place.</h1>
            <p className="ld-lede">
              TuraVector keeps your manuscripts, reviews, references and research projects together, with a clear record
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

        <section className="ld-section">
          <div className="ld-wrap ld-final">
            <h2 className="ld-h2">{user ? 'Pick up where you left off.' : 'Ready to sign in?'}</h2>
            <p className="muted">Accounts are created by your administrator.</p>
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
