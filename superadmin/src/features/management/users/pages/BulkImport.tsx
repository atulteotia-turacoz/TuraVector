import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Download, FileSpreadsheet, Upload } from 'lucide-react';
import { api, downloadFile, toFormData } from '@/lib/api';
import { useAuth } from '../../auth';
import { Field, PageHeader, Panel, useConfirm, useToast } from '@/components/ui';
import { apiError, useErrorToast, useFlash, type ActionResult } from '../shared';

const REQUIRED = [
  ['username', 'Unique username for login', 'john_doe'],
  ['email', 'Unique email address', 'john@example.com'],
  ['first_name', "User's first name", 'John'],
  ['last_name', "User's last name", 'Doe'],
  ['user_type', 'Type of user (must match existing types)', 'Student, Teacher, Reviewer, etc.'],
];
const OPTIONAL = [
  ['password', "User's password (auto-generated if empty)", 'MySecure123!'],
  ['phone', 'Phone number', '+1234567890'],
  ['address', 'Full address', '123 Main St, City'],
  ['is_manager', 'Manager status (true/false)', 'true, false'],
];

export default function BulkImport() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const flash = useFlash();
  const showError = useErrorToast();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [sendWelcome, setSendWelcome] = useState(true);
  const [skipErrors, setSkipErrors] = useState(false);
  const [fileError, setFileError] = useState('');
  const [busy, setBusy] = useState(false);
  const [organisation, setOrganisation] = useState('');
  // a superadmin chooses the workspace the imported users join
  const workspaces = useQuery({
    queryKey: ['create-options'],
    queryFn: async () => (await api.get('/api/users/create-options')).data as { organisations: { id: number; name: string }[] | null },
  });
  const organisations = workspaces.data?.organisations ?? null;

  // bulk_import_users_view: only managers (user_type == 'manager' or is_manager)
  useEffect(() => {
    if (user && !user.is_manager_like) {
      toast.error('You do not have permission to import users');
      navigate('/library/manage-users/', { replace: true });
    }
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const template = async (format: 'csv' | 'xlsx') => {
    try { await downloadFile('/api/users/bulk-import/template', { format }, `user_import_template.${format}`); }
    catch (e) { showError(e); }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) { toast.error('Please select a file to import.'); return; }
    if (organisations && !organisation) { toast.error('Please choose the workspace the users join.'); return; }
    const size = (file.size / 1024 / 1024).toFixed(2);
    if (!(await confirm({ title: 'Import users', message: `Are you sure you want to import users from "${file.name}" (${size} MB)?`, confirmLabel: 'Import' }))) return;
    setBusy(true);
    setFileError('');
    try {
      const { data } = await api.post<ActionResult & { redirect: string }>('/api/users/bulk-import',
        toFormData({ file, send_welcome_email: sendWelcome, skip_errors: skipErrors, organisation }));
      flash(data.messages);
      qc.invalidateQueries({ queryKey: ['users'] });
      if (data.redirect === 'manage_users') navigate('/library/manage-users/');
    } catch (err) {
      const info = apiError(err);
      if (info.fieldErrors?.file) setFileError(info.fieldErrors.file.join(', '));
      else showError(err);
    } finally { setBusy(false); }
  };

  return (
    <div className="stack-lg">
      <PageHeader title="Bulk Import Users"
        actions={<Link className="btn btn-secondary" to="/library/manage-users/"><ArrowLeft size={14} /> Back to Manage Users</Link>} />

      <Panel title="Download Import Template">
        <p className="muted">Download a template file with the correct format and sample data to help you prepare your user import file.</p>
        <div className="row">
          <button className="btn btn-secondary" onClick={() => template('csv')}><Download size={14} /> Download CSV Template</button>
          <button className="btn btn-secondary" onClick={() => template('xlsx')}><FileSpreadsheet size={14} /> Download Excel Template</button>
        </div>
      </Panel>

      <Panel title="Import Instructions">
        <ol className="users-list">
          <li>Download the template file in your preferred format (CSV or Excel)</li>
          <li>Fill in the user data following the format in the template</li>
          <li>Required fields: username, email, first_name, last_name, user_type</li>
          <li>Optional fields: password (auto-generated if empty), phone, address, is_manager</li>
          <li>Upload the completed file using the form below</li>
          <li>Review the import results and fix any errors</li>
        </ol>
      </Panel>

      <Panel title="Upload User Import File">
        <form className="stack" onSubmit={submit}>
          {organisations && (
            <Field label="Workspace" required help="Everyone in the file joins this university or organisation.">
              <select className="input" value={organisation} onChange={(e) => setOrganisation(e.target.value)}>
                <option value="">Select workspace...</option>
                {organisations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </Field>
          )}
          <Field label="Import File" help="Upload a CSV or Excel file containing user data" error={fileError || undefined}>
            <input className="input" type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </Field>
          <label className="check">
            <input type="checkbox" checked={sendWelcome} onChange={(e) => setSendWelcome(e.target.checked)} />
            <span>Send welcome email to new users</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={skipErrors} onChange={(e) => setSkipErrors(e.target.checked)} />
            <span>Skip rows with errors and continue importing<span className="field-help">If unchecked, the import will stop at the first error</span></span>
          </label>
          <div className="row">
            <button className="btn btn-primary" type="submit" disabled={busy}><Upload size={14} /> {busy ? 'Importing...' : 'Import Users'}</button>
            <Link className="btn btn-secondary" to="/library/manage-users/">Cancel</Link>
          </div>
        </form>
      </Panel>

      <Panel title="File Format Requirements">
        <div className="stack">
          <div className="section-title small">Required Columns:</div>
          <ColumnTable rows={REQUIRED} />
          <div className="section-title small">Optional Columns:</div>
          <ColumnTable rows={OPTIONAL} />
        </div>
      </Panel>
    </div>
  );
}

function ColumnTable({ rows }: { rows: string[][] }) {
  return (
    <div className="table-scroll">
      <table className="tbl">
        <thead><tr><th>Column Name</th><th>Description</th><th>Example</th></tr></thead>
        <tbody>{rows.map(([c, d, ex]) => <tr key={c}><td><code className="mono">{c}</code></td><td>{d}</td><td>{ex}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
