/**
 * Link References to a document version — port of templates/documents/link_references.html
 * (documents.views.link_references_view / unlink_reference_view,
 * URL /documents/version/<version_id>/link-references/).
 */
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Calendar, CheckCircle2, CheckSquare, Eye, Globe, Link2, Paperclip, Plus, PlusCircle, Search, Square, Unlink, User, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { Badge, Empty, ErrorNotice, Field, Loading, Panel, Spinner, useConfirm, useToast } from '@/components/ui';
import { type ReferenceLink, type ViewerDocument, type ViewerReference, type ViewerVersion, usePageData } from '../api';
import '../viewer.css';

interface LinkData {
  document: ViewerDocument;
  document_version: ViewerVersion;
  available_references: ViewerReference[];
  linked_references: ReferenceLink[];
}

export default function LinkReferencesPage() {
  const { versionId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = usePageData<LinkData>(['link-references', versionId], `/api/viewer/versions/${versionId}/link-references`);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (q.isLoading) return <Loading />;
  if (q.error) return (q.error.response?.data as any)?.redirect ? <Loading /> : <ErrorNotice error={q.error} />;
  if (!q.data) return null;
  const { document: doc, document_version: version, available_references: available, linked_references: linked } = q.data;

  const toggle = (id: number) => setSelected((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const selectAll = () => setSelected(new Set(available.map((r) => r.id)));
  const selectNone = () => setSelected(new Set());
  const count = selected.size;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (count === 0) { toast.warning('Please select at least one reference to link.'); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post(`/api/viewer/versions/${version.id}/link-references`, {
        reference_ids: Array.from(selected), notes,
      });
      (data.errors || []).forEach((m: string) => toast.error(m));
      if (data.message) toast.success(data.message);
      navigate(data.redirect);
    } catch (err) {
      toast.error(errorMessage(err));
      setSubmitting(false);
    }
  };

  const unlink = async (ref: ViewerReference) => {
    if (!(await confirm({ title: 'Unlink reference', message: 'Are you sure you want to unlink this reference?', confirmLabel: 'Unlink', danger: true }))) return;
    try {
      const { data } = await api.post(`/api/viewer/versions/${version.id}/unlink-reference/${ref.id}`);
      if (data.level === 'error') toast.error(data.message); else toast.success(data.message);
      await qc.invalidateQueries({ queryKey: ['viewer', 'link-references', versionId] });
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  return (
    <div className="vw-page">
      <nav className="small muted vw-crumbs" aria-label="breadcrumb">
        <Link to="/content-lab-management/dashboard/">Dashboard</Link> / <Link to={`/content-lab-management/document/${doc.id}/`}>{doc.document_number}</Link> /{' '}
        <Link to={`/content-lab-management/document/${doc.id}/history/`}>History</Link> / <span>Link References</span>
      </nav>
      <header className="page-header">
        <div className="grow">
          <div className="eyebrow">Link References to Document Version</div>
          <h1 className="row"><Link2 size={20} /> Link References to: {version.file_title_name}</h1>
          <p className="muted page-subtitle">Version: {version.version_number} | Document: {doc.document_number}</p>
        </div>
      </header>

      <div className="grid-2">
        <Panel title={<span className="row"><Paperclip size={15} /> Currently Linked References ({linked.length})</span>}>
          {linked.length === 0 ? (
            <Empty title="No references linked yet">Link references from the available list to organize and connect related documents.</Empty>
          ) : (
            <div className="stack">
              {linked.map((l) => (
                <div key={l.id} className="vw-card between">
                  <div className="grow">
                    <strong>{l.reference.reference_number}</strong>
                    <p>{l.reference.document_name}</p>
                    <div className="muted small">
                      <User size={12} /> Linked by: {l.linked_by ? (l.linked_by.full_name || l.linked_by.username) : ''}<br />
                      <Calendar size={12} /> {formatDateTime(l.linked_at)}
                    </div>
                    {l.notes && <div className="small status-accent vw-mt"><strong>Notes:</strong> {l.notes}</div>}
                  </div>
                  <div className="stack">
                    <Link to={`/content-lab-management/reference-library/${l.reference.id}/`} className="btn btn-secondary btn-sm btn-icon" title="View Details"><Eye size={14} /></Link>
                    <button className="btn btn-danger btn-sm btn-icon" title="Unlink" onClick={() => unlink(l.reference)}><Unlink size={14} /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title={<span className="row"><PlusCircle size={15} /> Available References to Link ({available.length})</span>}>
          {available.length === 0 ? (
            <Empty title="No available references"
              action={<Link to="/content-lab-management/reference-library/upload/" className="btn btn-primary"><Plus size={14} /> Upload New Reference</Link>}>
              <Search size={16} /> All your accessible references are either already linked or you haven't created any yet.
            </Empty>
          ) : (
            <form onSubmit={onSubmit} className="stack">
              <Field label="Notes (Optional)">
                <textarea className="input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
                  placeholder="Add notes about why you're linking these references..." />
              </Field>
              <div className="vw-select-list">
                <div className="between vw-select-counter">
                  {count === 0 ? <span className="muted">No references selected</span>
                    : <strong className="status-accent row"><CheckCircle2 size={14} /> {count} reference{count > 1 ? 's' : ''} selected</strong>}
                  <div className="row">
                    <button type="button" className="btn btn-secondary btn-sm" onClick={selectAll}><CheckSquare size={14} /> All</button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={selectNone}><X size={14} /> None</button>
                  </div>
                </div>
                {available.map((r) => {
                  const isSel = selected.has(r.id);
                  return (
                    <label key={r.id} className={`vw-select-item ${isSel ? 'is-selected' : ''}`}>
                      <input type="checkbox" name="reference_ids" value={r.id} checked={isSel} onChange={() => toggle(r.id)} />
                      <span className="grow">
                        <strong className="vw-block">{r.reference_number}</strong>
                        <span className="vw-block">{r.document_name}</span>
                        <span className="row wrap vw-mt">
                          <Badge tone="accent">{r.type_display}</Badge>
                          <Badge>{r.subtype_display}</Badge>
                          {r.therapeutic_area && <Badge>{r.therapeutic_area}</Badge>}
                        </span>
                        <span className="muted small vw-block vw-mt"><Globe size={12} /> {r.country}{r.ref_year ? <> <Calendar size={12} /> {r.ref_year}</> : null}</span>
                      </span>
                      <a href={`/content-lab-management/reference-library/${r.id}/`} className="btn btn-secondary btn-sm btn-icon" title="View Details"
                        onClick={(e) => { e.stopPropagation(); e.preventDefault(); window.open(`/content-lab-management/reference-library/${r.id}/`, '_blank'); }}>
                        <Eye size={14} />
                      </a>
                    </label>
                  );
                })}
              </div>
              <div className="between">
                <div className="row">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={selectAll}><CheckSquare size={14} /> Select All</button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={selectNone}><Square size={14} /> Select None</button>
                </div>
                <button type="submit" className={`btn ${count > 0 ? 'btn-primary' : 'btn-secondary'}`} disabled={count === 0 || submitting}>
                  {submitting ? <><Spinner /> Linking References...</>
                    : <><Link2 size={14} /> {count > 0 ? `Link ${count} Selected Reference${count > 1 ? 's' : ''}` : 'Link Selected References'}</>}
                </button>
              </div>
            </form>
          )}
        </Panel>
      </div>

      <div className="between vw-mt">
        <Link to={`/content-lab-management/document/${doc.id}/history/`} className="btn btn-secondary"><ArrowLeft size={14} /> Back to History</Link>
        <Link to="/content-lab-management/reference-library/" className="btn btn-secondary">Reference Library</Link>
      </div>
    </div>
  );
}
