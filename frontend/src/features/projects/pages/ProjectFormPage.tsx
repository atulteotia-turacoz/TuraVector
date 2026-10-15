/** templates/projects/project_form.html — create (project_create_view) and edit (project_edit_view). */
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Calendar, FlaskConical, Info, Plus, Save, UserRound, Users, X } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Field, PageHeader, Panel, useToast } from '@/components/ui';
import { formError, PageState, usePageData, type Author, type Choice, type FormErrorDetail } from '../shared';

interface Choices {
  project_types: Choice[]; client_types: Choice[]; therapeutic_areas: Choice[]; statuses: Choice[];
  priorities: Choice[]; author_types: Choice[];
}

type Values = Record<string, any>;

const EMPTY_AUTHOR: Author = { id: null, name: '', affiliation: '', email: '', author_type: 'other' };

const INITIAL: Values = {
  project_type: 'manuscript', project_type_other: '', client_type: 'internal', client_other: '', title: '',
  status: 'planning', client_poc_name: '', client_poc_email: '', has_authors: false, journal_name: '',
  therapeutic_area: 'oncology', therapeutic_area_other: '', sub_therapy_area: '', start_date: '',
  estimated_end_date: '', actual_end_date: '', description: '', research_field: '', keywords: '',
  priority: 'medium', budget: '',
};

export default function ProjectFormPage() {
  const { projectId } = useParams();
  const isEdit = !!projectId;
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();

  const choicesQ = useQuery({ queryKey: ['projects', 'choices'], queryFn: async () => (await api.get<Choices>('/api/projects/choices')).data, staleTime: Infinity });
  const editQ = usePageData<Values & { authors: Author[]; page_title: string }>(
    ['projects', 'edit', projectId], `/api/projects/${projectId}/edit`, `/journal-selector/projects/${projectId}/`, undefined, isEdit);

  const [values, setValues] = useState<Values>(INITIAL);
  const [authors, setAuthors] = useState<Author[]>([{ ...EMPTY_AUTHOR }]);
  const [errors, setErrors] = useState<FormErrorDetail | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isEdit || !editQ.data) return;
    const v: Values = { ...INITIAL };
    Object.keys(INITIAL).forEach((k) => { v[k] = editQ.data[k] ?? (k === 'has_authors' ? false : ''); });
    setValues(v);
    // inline formset: existing authors + one extra blank form
    setAuthors([...(editQ.data.authors || []).map((a) => ({ ...a, DELETE: false })), { ...EMPTY_AUTHOR }]);
  }, [isEdit, editQ.data]);

  const set = (k: string, v: unknown) => setValues((s) => ({ ...s, [k]: v }));
  // toggleOtherField(): hiding the "other" input clears its value
  const setWithOther = (k: string, v: string, otherKey: string) =>
    setValues((s) => ({ ...s, [k]: v, ...(v === 'other' || v === 'others' ? {} : { [otherKey]: '' }) }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors(null);
    const payload = { ...values, status: isEdit ? values.status : 'planning', authors: authors.map((a) => ({ ...a })) };
    try {
      if (isEdit) {
        await api.put(`/api/projects/${projectId}`, payload);
        await qc.invalidateQueries({ queryKey: ['projects'] });
        navigate(`/journal-selector/projects/${projectId}/`);
      } else {
        const { data } = await api.post('/api/projects', payload);
        toast.success(data.message);
        await qc.invalidateQueries({ queryKey: ['projects'] });
        navigate(`/journal-selector/projects/${data.id}/timeline/`);
      }
    } catch (err) {
      const fe = formError(err);
      if (fe) { setErrors(fe); toast.error(fe.message); window.scrollTo({ top: 0, behavior: 'smooth' }); }
      else toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (isEdit && (editQ.isLoading || editQ.error)) return <PageState q={editQ} />;
  const ch = choicesQ.data;
  const fieldErr = (k: string) => errors?.errors[k]?.[0];
  const opts = (list?: Choice[]) => list?.map((c) => <option key={c.value} value={c.value}>{c.label}</option>);
  const text = (k: string, label: ReactNode, props: Record<string, unknown> = {}) => (
    <Field label={label} error={fieldErr(k)} help={props.help as ReactNode}>
      <input className="input" value={values[k] ?? ''} onChange={(e) => set(k, e.target.value)}
        placeholder={props.placeholder as string} type={(props.type as string) || 'text'} step={props.step as string} />
    </Field>
  );
  const pageTitle = isEdit ? editQ.data?.page_title || 'Edit Project' : 'Create New Project';

  const updateAuthor = (i: number, patch: Partial<Author>) => setAuthors((list) => list.map((a, j) => (j === i ? { ...a, ...patch } : a)));
  const removeAuthor = (i: number) => setAuthors((list) => (list[i]!.id ? list.map((a, j) => (j === i ? { ...a, DELETE: true } : a)) : list.filter((_, j) => j !== i)));

  return (
    <div className="proj-narrow">
      <PageHeader title={pageTitle} />
      {errors && errors.non_field_errors.length > 0 && (
        <div className="notice notice-danger" style={{ marginBottom: 14 }}>{errors.non_field_errors.join(' ')}</div>
      )}
      {errors && Object.keys(errors.errors).length > 0 && (
        <div className="notice notice-warn" style={{ marginBottom: 14 }}>
          <div className="notice-title">Form validation errors:</div>
          <ul style={{ paddingLeft: 18 }}>
            {Object.entries(errors.errors).map(([f, list]) => <li key={f}><strong>{f}:</strong> {list.join(' ')}</li>)}
          </ul>
        </div>
      )}

      <form onSubmit={submit} className="stack-lg">
        <Panel title={<span className="row-tight"><Info size={15} /> Basic Project Information</span>}>
          <div className="form-grid">
            <Field label="Project Type" required error={fieldErr('project_type')}>
              <select className="input" value={values.project_type} onChange={(e) => setWithOther('project_type', e.target.value, 'project_type_other')}>{opts(ch?.project_types)}</select>
            </Field>
            {values.project_type === 'other'
              ? <Field label="If Other, Please Specify" error={fieldErr('project_type_other')}>
                  <input className="input" required value={values.project_type_other ?? ''} onChange={(e) => set('project_type_other', e.target.value)} />
                </Field>
              : <div />}
            <Field label="Client" required error={fieldErr('client_type')}>
              <select className="input" value={values.client_type} onChange={(e) => setWithOther('client_type', e.target.value, 'client_other')}>{opts(ch?.client_types)}</select>
            </Field>
            {values.client_type === 'other'
              ? <Field label="If Other, Please Specify" error={fieldErr('client_other')}>
                  <input className="input" required value={values.client_other ?? ''} onChange={(e) => set('client_other', e.target.value)} />
                </Field>
              : <div />}
            <div className="span-2">
              {text('title', <>Project Title <span className="req">*</span></>, { placeholder: 'Enter project title', help: 'Name of the project should be given' })}
            </div>
          </div>
        </Panel>

        <Panel title={<span className="row-tight"><UserRound size={15} /> Client Point of Contact</span>}>
          <div className="form-grid">
            {text('client_poc_name', 'Client POC Name', { placeholder: 'Client Point of Contact Name' })}
            {text('client_poc_email', 'Client POC Email', { placeholder: 'client@example.com', type: 'email' })}
          </div>
        </Panel>

        <Panel title={<span className="row-tight"><Users size={15} /> Authors</span>}>
          <label className="check">
            <input type="checkbox" checked={!!values.has_authors} onChange={(e) => set('has_authors', e.target.checked)} />
            <span>Does this project have authors?</span>
          </label>
          {values.has_authors && (
            <div style={{ marginTop: 16 }}>
              {authors.map((a, i) => a.DELETE ? null : (
                <div key={i} className="proj-author-row">
                  <div className="between" style={{ marginBottom: 10 }}>
                    <span className="small muted">Author {authors.slice(0, i + 1).filter((x) => !x.DELETE).length}</span>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeAuthor(i)}><X size={13} /> Remove</button>
                  </div>
                  <div className="form-grid">
                    <Field label="Author Name"><input className="input" placeholder="Author's full name" value={a.name} onChange={(e) => updateAuthor(i, { name: e.target.value })} /></Field>
                    <Field label="Author Type">
                      <select className="input" value={a.author_type} onChange={(e) => updateAuthor(i, { author_type: e.target.value })}>
                        <option value="other">Other Author</option>
                        <option value="corresponding">Corresponding Author</option>
                      </select>
                    </Field>
                    <Field label="Affiliation"><input className="input" placeholder="Author's institutional affiliation" value={a.affiliation} onChange={(e) => updateAuthor(i, { affiliation: e.target.value })} /></Field>
                    <Field label="Email"><input className="input" type="email" placeholder="author@example.com" value={a.email} onChange={(e) => updateAuthor(i, { email: e.target.value })} /></Field>
                  </div>
                </div>
              ))}
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAuthors((l) => [...l, { ...EMPTY_AUTHOR }])}><Plus size={13} /> Add Author</button>
            </div>
          )}
        </Panel>

        <Panel title={<span className="row-tight"><FlaskConical size={15} /> Research Information</span>}>
          <div className="form-grid">
            <div className="span-2">{text('journal_name', 'Journal Name', { placeholder: 'Journal name (if available)' })}</div>
            <Field label="Therapeutic Area" required error={fieldErr('therapeutic_area')}>
              <select className="input" value={values.therapeutic_area} onChange={(e) => setWithOther('therapeutic_area', e.target.value, 'therapeutic_area_other')}>{opts(ch?.therapeutic_areas)}</select>
            </Field>
            {values.therapeutic_area === 'others'
              ? <Field label="If Others, Please Specify" error={fieldErr('therapeutic_area_other')}>
                  <input className="input" required value={values.therapeutic_area_other ?? ''} onChange={(e) => set('therapeutic_area_other', e.target.value)} />
                </Field>
              : <div />}
            <div className="span-2">{text('sub_therapy_area', 'Sub Therapeutic Area', { placeholder: 'Sub therapeutic area' })}</div>
          </div>
        </Panel>

        <Panel title={<span className="row-tight"><Calendar size={15} /> Project Timeline</span>}>
          <div className="grid-3">
            {text('start_date', <>Project Start Date <span className="req">*</span></>, { type: 'date' })}
            {text('estimated_end_date', <>Estimated End Date <span className="req">*</span></>, { type: 'date' })}
            {isEdit && text('actual_end_date', 'Actual End Date', { type: 'date', help: 'To be filled after all milestones are completed' })}
          </div>
        </Panel>

        <Panel title={<span className="row-tight"><Info size={15} /> Additional Information</span>}>
          <div className="form-grid">
            <div className="span-2">
              <Field label="Description" error={fieldErr('description')}>
                <textarea className="input" rows={4} placeholder="Project description" value={values.description ?? ''} onChange={(e) => set('description', e.target.value)} />
              </Field>
            </div>
            {text('research_field', 'Research Field', { placeholder: 'e.g., Machine Learning, Biology, Chemistry' })}
            {text('keywords', 'Keywords', { placeholder: 'Comma-separated keywords' })}
            <Field label="Priority" error={fieldErr('priority')}>
              <select className="input" value={values.priority} onChange={(e) => set('priority', e.target.value)}>{opts(ch?.priorities)}</select>
            </Field>
            {isEdit ? (
              <Field label="Status" error={fieldErr('status')}>
                <select className="input" value={values.status} onChange={(e) => set('status', e.target.value)}>{opts(ch?.statuses)}</select>
              </Field>
            ) : <div />}
            {text('budget', 'Budget ($)', { type: 'number', step: '0.01', placeholder: '0.00' })}
          </div>
        </Panel>

        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <Link to={isEdit ? `/journal-selector/projects/${projectId}/` : '/journal-selector/projects/'} className="btn btn-secondary"><X size={14} /> Cancel</Link>
          <button type="submit" className="btn btn-primary" disabled={saving}><Save size={14} /> {isEdit ? 'Update Project' : 'Create Project'}</button>
        </div>
      </form>
    </div>
  );
}
