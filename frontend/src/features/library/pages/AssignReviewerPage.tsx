/** Port of templates/library/assign_reviewer.html (library.views.assign_reviewer_view). */
import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Info, Search, UserPlus, Users, X } from 'lucide-react';
import { api } from '@/lib/api';
import { formatDate, initials } from '@/lib/format';
import { BackLink, Badge, ErrorNotice, Field, Loading, PageHeader, Spinner, StageStatus, useToast } from '@/components/ui';
import { STAGE_BADGE, useActionFeedback, useLibraryPage } from '../api';
import '../library.css';

interface Reviewer { id: number; first_name: string; last_name: string; email: string; user_type_title: string }
interface Resp {
  document: { id: number; document_name: string; document_number: string; document_type: string | null; brand: string | null; country: string | null; project: string | null };
  version: { id: number; version_number: string; stage_status: number; file_title_name: string; created_at: string; created_by: string };
  reviewers: Reviewer[];
  today: string;
  assigned_by: string;
}

export default function AssignReviewerPage() {
  const { documentId } = useParams();
  const toast = useToast();
  const feedback = useActionFeedback();
  const q = useLibraryPage<Resp>(['assign-reviewer', documentId], `/api/library/documents/${documentId}/assign-reviewer`);
  const [reviewerId, setReviewerId] = useState('');
  // Default review date: 7 days from today (same toISOString() computation as the template)
  const [reviewDate, setReviewDate] = useState(() => new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]);
  const [remarks, setRemarks] = useState('');
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('');

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNotice error={q.error} />;
  const { document: doc, version, reviewers, today, assigned_by } = q.data!;
  const stage = STAGE_BADGE[version.stage_status];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!reviewerId) { toast.error('Please select a reviewer'); return; }
    if (!reviewDate) { toast.error('Please set a review due date'); return; }
    const selected = new Date(reviewDate);
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    if (selected < now) { toast.error('Review date cannot be in the past'); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/api/library/documents/${documentId}/assign-reviewer`, {
        reviewer_id: reviewerId, review_date: reviewDate, remarks,
      });
      feedback.success(data, `/content-lab-management/document/${doc.id}/`);
    } catch (err) {
      feedback.failure(err);
      setBusy(false);
    }
  };

  const q2 = filter.trim().toLowerCase();
  const shown = q2 ? reviewers.filter((r) => `${r.first_name} ${r.last_name} ${r.email} ${r.user_type_title}`.toLowerCase().includes(q2)) : reviewers;
  const selected = reviewers.find((r) => String(r.id) === reviewerId);

  return (
    <div className="ar">
      <BackLink to={`/content-lab-management/document/${documentId}/`}>Back to document</BackLink>
      <PageHeader title="Assign Reviewer" subtitle={<>{doc.document_name} · <span className="mono">{version.version_number}</span></>} />

      <div className="ar-grid">
        {/* Left: document + assignment form */}
        <form className="panel" onSubmit={submit} noValidate>
          <div className="panel-head"><h2 className="row-tight"><Info size={15} /> Assignment details</h2></div>
          <div className="panel-body">
            <dl className="ar-facts">
              <div><dt>Document</dt><dd>{doc.document_name}<span className="ar-sub mono">{doc.document_number}</span></dd></div>
              <div><dt>Version</dt><dd><span className="mono">{version.version_number}</span> <Badge tone="accent">Latest Version</Badge></dd></div>
              <div><dt>Current status</dt><dd>{stage ? <StageStatus label={stage.label} tone={stage.tone} /> : '-'}</dd></div>
              <div><dt>File</dt><dd>{version.file_title_name}<span className="ar-sub">Created {formatDate(version.created_at)} by {version.created_by}</span></dd></div>
              <div><dt>Type · Brand · Country</dt><dd>{doc.document_type || '-'} · {doc.brand || '-'} · {doc.country || '-'}</dd></div>
              <div><dt>Project</dt><dd>{doc.project || 'No Project'}</dd></div>
            </dl>

            <div className="ar-divider" />

            <div className="field">
              <span className="field-label">Reviewer<span className="req">*</span></span>
              {selected ? (
                <div className="ar-selected">
                  <span className="avatar">{initials(`${selected.first_name} ${selected.last_name}`)}</span>
                  <span className="grow" style={{ minWidth: 0 }}>
                    <span className="ar-reviewer-name">{selected.first_name} {selected.last_name}</span>
                    <span className="ar-reviewer-meta truncate">{selected.user_type_title}{selected.email ? ` · ${selected.email}` : ''}</span>
                  </span>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setReviewerId('')}>Change</button>
                </div>
              ) : (
                <div className="ar-selected is-empty">Select a reviewer from the list on the right.</div>
              )}
            </div>

            <div className="form-grid ar-fields">
              <Field label="Review Due Date" required help="Set the deadline for completing the review.">
                <input type="date" className="input" min={today} value={reviewDate} onChange={(e) => setReviewDate(e.target.value)} required />
              </Field>
              <Field label="Assigned By">
                <input className="input" value={`${assigned_by} · ${formatDate(`${today}T12:00:00`)}`} disabled />
              </Field>
              <div className="span-2">
                <Field label="Assignment Remarks" help="Optional: specific areas to focus on during review.">
                  <textarea className="input" rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)}
                    placeholder="Add any specific instructions or notes for the reviewer..." />
                </Field>
              </div>
            </div>
          </div>
          <div className="panel-foot between">
            <Link to={`/content-lab-management/document/${doc.id}/`} className="btn btn-secondary"><X size={14} /> Cancel</Link>
            <button type="submit" className="btn btn-primary" disabled={busy || reviewers.length === 0}>
              {busy ? <><Spinner /> Assigning...</> : <><UserPlus size={14} /> Assign Reviewer</>}
            </button>
          </div>
        </form>

        {/* Right: available reviewers */}
        <aside className="panel ar-side">
          <div className="panel-head">
            <h2 className="row-tight"><Users size={15} /> Available reviewers <span className="faint small">({reviewers.length})</span></h2>
          </div>
          {reviewers.length > 6 && (
            <div className="ar-filter-wrap">
              <div className="search-input ar-filter">
                <Search size={14} />
                <input className="input" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter reviewers…" aria-label="Filter reviewers" />
              </div>
            </div>
          )}
          {reviewers.length === 0 ? (
            <div className="panel-body">
              <div className="notice notice-warn">
                <div className="notice-title row-tight"><AlertTriangle size={14} /> No Reviewers Available</div>
                There are no active reviewers or teachers in the system. Please contact an administrator to add reviewers.
              </div>
            </div>
          ) : (
            <div className="ar-reviewers" role="radiogroup" aria-label="Select Reviewer">
              {shown.map((r) => {
                const on = String(r.id) === reviewerId;
                return (
                  <label key={r.id} className={`ar-reviewer ${on ? 'is-selected' : ''}`}>
                    <input type="radio" name="reviewer" value={r.id} checked={on} onChange={() => setReviewerId(String(r.id))} />
                    <span className="avatar">{initials(`${r.first_name} ${r.last_name}`)}</span>
                    <span className="grow" style={{ minWidth: 0 }}>
                      <span className="ar-reviewer-name">{r.first_name} {r.last_name}</span>
                      <span className="ar-reviewer-meta truncate">{r.user_type_title}{r.email ? ` · ${r.email}` : ''}</span>
                    </span>
                    {on && <CheckCircle2 size={16} className="ar-check" />}
                  </label>
                );
              })}
              {shown.length === 0 && <div className="small muted" style={{ padding: '12px 16px' }}>No reviewer matches “{filter}”.</div>}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
