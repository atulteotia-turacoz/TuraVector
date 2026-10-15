import { HardHat } from 'lucide-react';
import { Badge, PageHeader, Panel } from '@/components/ui';
import './tools.css';

/** documents/conference_selector.html — static "under development" page. */
export default function ConferenceSelectorPage() {
  return (
    <div className="stack-lg">
      <PageHeader title="Conference Selector" />
      <Panel>
        <div className="tools-coming">
          <HardHat size={40} style={{ margin: '0 auto', color: 'var(--accent)' }} />
          <h2>The Page is under development.</h2>
          <p className="muted" style={{ marginBottom: 14 }}>This Functionality is coming soon</p>
          <Badge tone="accent">Coming Soon</Badge>
        </div>
      </Panel>
    </div>
  );
}
