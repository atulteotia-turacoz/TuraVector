/**
 * Tabbed permission picker from create_role.html / edit_role.html:
 * dashboards as tabs, modules as collapsible groups, Select All / Clear All at every level,
 * plus the "Permission summary" (and "Changes" on edit) side panel.
 */
import { useState } from 'react';
import { ChevronDown, ChevronRight, CheckSquare, Square, RotateCcw } from 'lucide-react';
import { Badge, Tabs } from '@/components/ui';
import type { PermissionGroup, PermissionItem } from '../shared';

function level(p: PermissionItem, includeManage: boolean): { label: string; tone?: 'accent' | 'ok' | 'warn' | 'danger' } | null {
  if (p.action === 'view') return { label: 'Basic', tone: 'ok' };
  // Django template uses substring tests: `action in 'create,edit,delete'`
  if ('create,edit,delete'.includes(p.action)) return { label: 'Modify', tone: 'warn' };
  if ((includeManage ? 'approve,review,assign,manage' : 'approve,review,assign').includes(p.action)) return { label: 'Admin', tone: 'danger' };
  return null;
}

export function PermissionMatrix({ groups, selected, onChange, original, totalPermissions, mode }: {
  groups: PermissionGroup[];
  selected: Set<number>;
  onChange: (next: Set<number>) => void;
  original?: Set<number>;
  totalPermissions: number;
  mode: 'create' | 'edit';
}) {
  const [tab, setTab] = useState(groups[0]?.dashboard ?? '');
  const [open, setOpen] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    groups.forEach((g) => { if (g.modules[0]) init[`${g.dashboard}|${g.modules[0].module}`] = true; });
    return init;
  });
  const all = groups.flatMap((g) => g.modules.flatMap((m) => m.permissions));

  const setMany = (ids: number[], on: boolean) => {
    const next = new Set(selected);
    ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
    onChange(next);
  };
  const toggle = (id: number) => setMany([id], !selected.has(id));

  const stats = { view: 0, create: 0, edit: 0, delete: 0, other: 0 };
  all.filter((p) => selected.has(p.id)).forEach((p) => {
    if (p.action in stats) stats[p.action as keyof typeof stats]++;
    else stats.other++;
  });
  const added = original ? [...selected].filter((id) => !original.has(id)).length : 0;
  const removed = original ? [...original].filter((id) => !selected.has(id)).length : 0;
  const current = groups.find((g) => g.dashboard === tab) ?? groups[0];

  return (
    <div className="detail-grid">
      <div className="stack">
        <div className="row wrap between">
          <div className="row-tight wrap">
            <span className="small muted">Quick Actions:</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setMany(all.map((p) => p.id), true)}><CheckSquare size={13} /> Select All</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setMany(all.map((p) => p.id), false)}><Square size={13} /> Clear All</button>
            {mode === 'edit' && original && (
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange(new Set(original))}><RotateCcw size={13} /> Reset to Original</button>
            )}
          </div>
          <span className="small muted">Total Permissions Available: <strong>{totalPermissions}</strong></span>
        </div>

        {groups.length > 0 && <Tabs tabs={groups.map((g) => ({ value: g.dashboard, label: g.dashboard }))} value={current.dashboard} onChange={setTab} />}

        {current && (
          <div className="stack">
            <div className="row-tight wrap">
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMany(current.modules.flatMap((m) => m.permissions.map((p) => p.id)), true)}>Select All in {current.dashboard}</button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMany(current.modules.flatMap((m) => m.permissions.map((p) => p.id)), false)}>Clear All in {current.dashboard}</button>
            </div>
            <div className="users-accordion">
              {current.modules.map((m) => {
                const key = `${current.dashboard}|${m.module}`;
                const isOpen = !!open[key];
                const ids = m.permissions.map((p) => p.id);
                return (
                  <div key={key} className="users-acc-item">
                    <button type="button" className="users-acc-head" onClick={() => setOpen((o) => ({ ...o, [key]: !isOpen }))} aria-expanded={isOpen}>
                      {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      <span className="grow">{m.module}</span>
                      <Badge>{m.permissions.length} permissions</Badge>
                    </button>
                    {isOpen && (
                      <div className="users-acc-body">
                        <div className="row-tight">
                          <button type="button" className="act act-accent" onClick={() => setMany(ids, true)}>Select All</button>
                          <button type="button" className="act" onClick={() => setMany(ids, false)}>Clear All</button>
                        </div>
                        <div className="users-perm-grid">
                          {m.permissions.map((p) => {
                            const lv = level(p, mode === 'edit');
                            return (
                              <label key={p.id} className="check" title={mode === 'edit' ? p.description : undefined}>
                                <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
                                <span>
                                  {p.action_display}
                                  {mode === 'edit' && p.action === 'manage' && p.module === 'cl_library' && <span className="tiny muted"> (ZIP Files)</span>}
                                  {lv && <> <Badge tone={lv.tone}>{lv.label}</Badge></>}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="stack">
        <div className="well">
          <div className="section-title small">PERMISSION SUMMARY</div>
          <dl className="kv users-kv-tight">
            <dt>Total Selected</dt><dd>{selected.size}</dd>
            <dt>View Permissions</dt><dd>{stats.view}</dd>
            <dt>Create Permissions</dt><dd>{stats.create}</dd>
            <dt>Edit Permissions</dt><dd>{stats.edit}</dd>
            <dt>Delete Permissions</dt><dd>{stats.delete}</dd>
            <dt>Other Permissions</dt><dd>{stats.other}</dd>
          </dl>
        </div>
        {mode === 'edit' && (
          <div className="well">
            <div className="section-title small">CHANGES</div>
            <dl className="kv users-kv-tight">
              <dt>Permissions Added</dt><dd>{added}</dd>
              <dt>Permissions Removed</dt><dd>{removed}</dd>
            </dl>
          </div>
        )}
        <div className="well">
          <div className="section-title small">QUICK TIPS</div>
          <ul className="users-list small">
            {mode === 'edit' ? (<>
              <li>Review current permissions carefully</li>
              <li>Add new permissions as needed</li>
              <li>Remove unnecessary permissions</li>
              <li>Changes affect all users with this role</li>
            </>) : (<>
              <li>Start with basic view permissions</li>
              <li>Add create/edit permissions as needed</li>
              <li>Delete permissions should be limited</li>
              <li>Review admin permissions carefully</li>
            </>)}
          </ul>
        </div>
      </div>
    </div>
  );
}
