import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check, Save, X } from 'lucide-react';
import { api, errorMessage, toFormData } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { ErrorNotice, Field, Loading, PageHeader, Panel, Spinner, useConfirm, useToast } from '@/components/ui';
import { CATEGORY_META, type CategoryItem, type CategoryKind } from './api';
import './tools.css';

/** documents/categories/category_add.html + category_edit.html */
export default function CategoryFormPage({ kind }: { kind: CategoryKind }) {
  const meta = CATEGORY_META[kind];
  const { itemId } = useParams();
  const editing = !!itemId;
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);

  const q = useQuery({
    queryKey: ['tools', 'category', kind, itemId],
    enabled: editing,
    queryFn: async () => (await api.get<{ item: CategoryItem }>(`/api/tools/categories/${kind}/${itemId}`)).data.item,
  });
  useEffect(() => {
    if (q.data) { setName(q.data.name); setCode(q.data.code_name || ''); }
  }, [q.data]);

  const isCountry = kind === 'countries';
  const codeLabel = isCountry ? 'Country Code' : 'Brand Code';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!name.trim() || (meta.hasCode && !code.trim())) return; // browser "required" validation
    setBusy(true);
    try {
      const url = editing ? `/api/tools/categories/${kind}/${itemId}` : `/api/tools/categories/${kind}`;
      const { data } = await api.post(url, toFormData({ name, ...(meta.hasCode ? { code_name: code } : {}) }));
      toast.success(data.message);
      qc.invalidateQueries({ queryKey: ['tools', 'categories', kind] });
      navigate(meta.listPath);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally { setBusy(false); }
  };

  const toggle = async () => {
    const item = q.data!;
    const ok = await confirm({
      message: `Are you sure you want to ${item.is_active ? 'deactivate' : 'activate'} this ${meta.singular.toLowerCase()}?`,
      confirmLabel: item.is_active ? 'Deactivate' : 'Activate', danger: item.is_active,
    });
    if (!ok) return;
    try {
      const { data } = await api.post(`/api/tools/categories/${kind}/${item.id}/toggle`);
      toast.success(data.message);
      qc.invalidateQueries({ queryKey: ['tools', 'categories', kind] });
      navigate(meta.listPath);
    } catch (err) { toast.error(errorMessage(err)); }
  };

  if (editing && q.isLoading) return <Loading />;
  if (editing && q.error) return <ErrorNotice error={q.error} />;
  const item = q.data;

  return (
    <div className="tools-narrow stack-lg">
      <Link className="btn btn-ghost" to={meta.listPath}><ArrowLeft size={14} /> Back to {meta.plural}</Link>
      <PageHeader title={editing ? `Edit ${meta.singular}` : `Add New ${meta.singular}`} />

      {editing && item && (
        <div className="well between wrap">
          <div>
            <div className="small" style={{ fontWeight: 600 }}>Current Status</div>
            <div className="small muted">This {meta.singular.toLowerCase()} is currently{' '}
              {item.is_active ? <span className="badge badge-ok">Active</span> : <span className="badge">Inactive</span>}</div>
          </div>
          <div className="small muted">Created: {formatDate(item.created_at)}<br />Updated: {formatDate(item.updated_at)}</div>
        </div>
      )}

      <Panel>
        <form onSubmit={submit} noValidate>
          <Field label={`${meta.singular} Name`} required
            error={touched && !name.trim() ? `Please provide a valid ${meta.singular.toLowerCase()} name.` : undefined}>
            <input className={`input ${touched && !name.trim() ? 'error' : ''}`} autoFocus maxLength={255} value={name}
              placeholder={`Enter ${meta.singular.toLowerCase()} name`} onChange={(e) => setName(e.target.value)}
              onFocus={(e) => editing && e.target.select()} />
          </Field>
          {meta.hasCode && (
            <Field label={codeLabel} required
              help={isCountry ? 'Use standard country codes (2-10 characters)' : 'Use unique brand identifier (up to 50 characters)'}
              error={touched && !code.trim() ? 'Please provide a valid code.' : undefined}>
              <input className={`input ${touched && !code.trim() ? 'error' : ''}`} maxLength={isCountry ? 10 : 50} value={code}
                placeholder={isCountry ? 'e.g., US, UK, CA' : 'e.g., BRAND01, BRAND02'} onChange={(e) => setCode(e.target.value)} />
            </Field>
          )}
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 20 }}>
            <Link className="btn btn-secondary" to={meta.listPath}><X size={14} /> Cancel</Link>
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy ? <Spinner /> : <Save size={14} />} {editing ? 'Update' : 'Save'} {meta.singular}
            </button>
          </div>
        </form>
      </Panel>

      {editing && item && (
        <Panel title="Additional Actions">
          <div className="between wrap">
            <div>
              <div style={{ fontWeight: 600 }}>Status Management</div>
              <div className="small muted">
                {item.is_active
                  ? `Deactivate this ${meta.singular.toLowerCase()} to hide it from selection menus`
                  : `Activate this ${meta.singular.toLowerCase()} to make it available for selection`}
              </div>
            </div>
            <button className={`btn ${item.is_active ? 'btn-secondary' : 'btn-primary'}`} onClick={toggle}>
              {item.is_active ? <><X size={14} /> Deactivate</> : <><Check size={14} /> Activate</>}
            </button>
          </div>
        </Panel>
      )}

      <div className="notice notice-accent">
        <div className="notice-title">Information</div>
        {editing ? meta.editInfo : <>{meta.addInfo} All new {meta.singular.toLowerCase()}s are active by default and will be available for selection during document upload.</>}
      </div>
    </div>
  );
}
