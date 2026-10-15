/** Port of templates/documents/notifications.html (notifications_view). */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, BellOff, Check, Clock, ExternalLink, Eye, Home, Info, RefreshCw, RotateCw, Upload, User, X } from 'lucide-react';
import { api } from '@/lib/api';
import { Badge, Empty, ErrorNotice, Loading, PageHeader, Panel, Spinner, useToast } from '@/components/ui';
import { timesince, useTimezoneAutoDetect } from './utils';
import './auth.css';

interface NotificationItem {
  id: number;
  document_type: string;
  document_type_display: string;
  description: string;
  document_id: number;
  sender: string;
  sent_for: string;
  is_seen: boolean;
  created_at: string;
}
interface NotificationsPage { unread_count: number; total: number; notifications: NotificationItem[] }

const ICONS: Record<string, JSX.Element> = {
  document_upload: <Upload size={15} />,
  review_request: <Eye size={15} />,
  document_approved: <Check size={15} />,
  document_rejected: <X size={15} />,
  version_updated: <RotateCw size={15} />,
};

export default function NotificationsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  useTimezoneAutoDetect();
  const q = useQuery({
    queryKey: ['auth', 'notifications-page'],
    queryFn: async () => (await api.get('/api/documents/notifications')).data as NotificationsPage,
    staleTime: 0,
    gcTime: 0,
  });
  const [totalLabel, setTotalLabel] = useState<number | null>(null);
  const [opened, setOpened] = useState<Set<number>>(new Set());
  const [refreshing, setRefreshing] = useState(false);
  const lastCount = useRef<number | null>(null);

  // The full page marks everything as seen — keep the bell in the top bar in sync.
  useEffect(() => {
    if (q.data) {
      lastCount.current = q.data.total;
      void qc.invalidateQueries({ queryKey: ['notifications', 'recent'] });
    }
  }, [q.data, qc]);

  // Django polled get_notifications_api every 10s: updates the header badge and the "N total" badge,
  // and shows a toast when the list grew.
  const poll = useCallback(async () => {
    try {
      const { data } = await api.get('/api/notifications/recent');
      qc.setQueryData(['notifications', 'recent'], data);
      const len: number = data.notifications.length;
      if (lastCount.current !== null && len > lastCount.current) toast.info('You have new notifications!');
      lastCount.current = len;
      setTotalLabel(len);
    } catch (e) {
      console.error('Error updating notifications:', e);
    }
  }, [qc, toast]);

  useEffect(() => {
    if (!q.data) return;
    void poll();
    const id = window.setInterval(poll, 10000);
    return () => window.clearInterval(id);
  }, [q.data, poll]);

  const manualRefresh = async () => {
    setRefreshing(true);
    void poll();
    window.setTimeout(async () => {
      setTotalLabel(null);
      setOpened(new Set());
      await q.refetch();
      setRefreshing(false);
    }, 1000);
  };

  if (q.isLoading) return <Loading />;
  if (q.isError) return <ErrorNotice error={q.error} />;
  const data = q.data!;
  const items = data.notifications;

  return (
    <div className="stack-lg">
      <PageHeader title="Notifications" />
      <Panel
        title={<span className="row-tight"><Bell size={15} /> Your Notifications</span>}
        actions={<>
          <button className="btn btn-secondary btn-sm" onClick={manualRefresh} disabled={refreshing}>
            {refreshing ? <><Spinner /> Refreshing...</> : <><RefreshCw size={13} /> Refresh</>}
          </button>
          <Badge tone="accent">{totalLabel ?? data.total} total</Badge>
        </>}
        flush
      >
        {items.length === 0 ? (
          <Empty
            title={<span className="row-tight" style={{ justifyContent: 'center' }}><BellOff size={18} /> No Notifications</span>}
            action={<Link to="/content-lab-management/dashboard/" className="btn btn-primary"><Home size={14} /> Go to Dashboard</Link>}
          >
            You don't have any notifications yet. When documents are uploaded, reviewed, or updated, you'll see them here.
          </Empty>
        ) : (
          <div>
            {items.map((n) => {
              const unread = !n.is_seen && !opened.has(n.id);
              return (
                <div key={n.id} className={`au-notif ${unread ? 'is-unread' : ''}`}>
                  <div className={`au-notif-icon t-${n.document_type}`}>{ICONS[n.document_type] ?? <Info size={15} />}</div>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="between" style={{ alignItems: 'flex-start' }}>
                      <div style={{ minWidth: 0 }}>
                        <h3>{n.document_type_display}</h3>
                        <p>{n.description}</p>
                        <span className="small faint row-tight">
                          <User size={12} /> {n.sender}{n.sent_for ? ` • ${n.sent_for}` : ''}
                        </span>
                      </div>
                      <div className="right nowrap">
                        <div className="small muted row-tight"><Clock size={12} /> {timesince(n.created_at)} ago</div>
                        {unread && <div style={{ marginTop: 4 }}><Badge tone="ok">New</Badge></div>}
                      </div>
                    </div>
                  </div>
                  {!!n.document_id && (
                    <Link to={n.document_type === 'invoice' ? `/content-lab-management/invoices/${n.document_id}/` : `/content-lab-management/document/${n.document_id}/`} className="btn btn-secondary btn-sm"
                      onClick={() => setOpened((s) => new Set(s).add(n.id))}>
                      <ExternalLink size={13} /> View
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Panel>
      {items.length > 20 && (
        <div className="well center muted">Showing latest 20 notifications. Older notifications are automatically archived.</div>
      )}
    </div>
  );
}
