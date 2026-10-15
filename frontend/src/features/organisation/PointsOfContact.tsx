/**
 * Dashboard section for a university / organisation admin: the workspace's own points of contact
 * (always shown — with a button to assign one when there is none) and, below them in the same panel,
 * the Turacoz team assigned to the workspace (PoCs and Reviewers), once there is one.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Mail, Phone, Plus, UserPlus } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { Badge, Field, Modal, Panel, SearchSelect, useToast } from '@/components/ui';
import './organisation.css';

interface Contact { user_id: number; name: string; username: string; email: string; phone: string | null; designation: string }
interface TeamMember extends Contact { role: 'poc' | 'reviewer' | 'finance'; role_label: string; is_active: boolean }
interface Contacts { pocs: Contact[]; turacoz: TeamMember[] }
interface MemberOption { user_id: number; username: string; first_name: string; last_name: string; is_poc: boolean }

export function PointsOfContact() {
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [memberId, setMemberId] = useState('');
  const [title, setTitle] = useState('');
  const contacts = useQuery({
    queryKey: ['org', 'contacts'],
    queryFn: async () => (await api.get('/api/org/contacts')).data as Contacts,
    enabled: !!user?.is_org_admin,
  });
  const members = useQuery({
    queryKey: ['org', 'members', 'active'],
    queryFn: async () => (await api.get('/api/org/members', { params: { status: 'active' } })).data.members as MemberOption[],
    enabled: !!user?.is_org_admin && adding,
  });
  if (!user?.is_org_admin || !contacts.data) return null;
  const orgName = user.organisation?.name ?? 'Our';
  // the Turacoz team assigned to us: PoCs first, then reviewers
  const team = contacts.data.turacoz.filter((t) => t.is_active)
    .sort((a, b) => (a.role === b.role ? a.name.localeCompare(b.name) : a.role === 'poc' ? -1 : 1));
  const noPocs = contacts.data.pocs.length === 0;
  const close = () => { setAdding(false); setMemberId(''); setTitle(''); };
  const options = (members.data ?? []).filter((m) => !m.is_poc)
    .map((m) => ({ value: String(m.user_id), label: `${`${m.first_name} ${m.last_name}`.trim() || m.username} (${m.username})` }));

  const add = async () => {
    try {
      const { data } = await api.post(`/api/org/members/${memberId}/poc`, { is_poc: true, designation: title });
      toast.success(data.message);
      close();
      void qc.invalidateQueries({ queryKey: ['org'] });
    } catch (err) { toast.error(errorMessage(err)); }
  };

  return (
    <div className="poc-row">
      <Panel title={`${orgName} points of contact`}
        actions={!noPocs && <div className="row-tight">
          <button className="btn btn-secondary btn-sm" onClick={() => setAdding(true)}><Plus size={13} /> Add PoC</button>
          <Link className="act small" to="/content-lab-management/organisation/?tab=pocs">Manage</Link>
        </div>}>
        {noPocs ? (
          <div className="poc-empty">
            <div>
              <div className="org-name">No point of contact assigned yet</div>
              <div className="small muted">Choose who Turacoz should reach about your {user.organisation?.kind === 'organisation' ? 'organisation' : 'university'}.</div>
            </div>
            <button className="btn btn-primary" onClick={() => setAdding(true)}><UserPlus size={14} /> Assign PoC</button>
          </div>
        ) : <ContactCards people={contacts.data.pocs} />}
        {team.length > 0 && (
          <div className="poc-turacoz">
            <div className="poc-label">Your Turacoz team</div>
            <ul className="poc-team">
              {team.map((t) => (
                <li key={`${t.user_id}-${t.role}`}>
                  <span className="grow" style={{ minWidth: 0 }}>
                    <span className="org-name">{t.name}</span>
                    <a className="tiny faint poc-team-mail" href={`mailto:${t.email}`}>{t.email}</a>
                  </span>
                  <Badge tone={t.role === 'poc' ? 'accent' : undefined}>{t.role_label}</Badge>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
      <Modal open={adding} onClose={close} title="Assign a point of contact"
        footer={<>
          <button className="btn btn-secondary" onClick={close}>Cancel</button>
          <button className="btn btn-primary" disabled={!memberId} onClick={add}><UserPlus size={14} /> Assign</button>
        </>}>
        <div className="stack">
          <Field label="Member" required>
            <SearchSelect options={options} value={memberId} onChange={(v) => setMemberId(String(v ?? ''))}
              placeholder={members.isLoading ? 'Loading members…' : 'Choose a member…'} />
          </Field>
          <Field label="Designation" help="Shown to Turacoz, e.g. Dean, Principal, Research coordinator.">
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Designation" />
          </Field>
        </div>
      </Modal>
    </div>
  );
}

function ContactCards({ people }: { people: Contact[] }) {
  return (
    <ul className="poc-cards">
      {people.map((p) => (
        <li key={p.user_id}>
          <div className="org-name">{p.name}</div>
          {p.designation && <div className="tiny faint">{p.designation}</div>}
          <div className="poc-contact small">
            <a href={`mailto:${p.email}`}><Mail size={12} /> {p.email}</a>
            {p.phone && <a href={`tel:${p.phone}`}><Phone size={12} /> {p.phone}</a>}
          </div>
        </li>
      ))}
    </ul>
  );
}
