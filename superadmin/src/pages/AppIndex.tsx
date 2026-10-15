import { useParams } from 'react-router-dom';
import { useIndex } from '@/lib/admin';
import { Empty, ErrorNotice, Loading, PageHeader } from '@/components/ui';
import { Crumbs } from '@/components/Shell';
import { AppPanel } from './Dashboard';

export default function AppIndex() {
  const { app } = useParams();
  const { data, isLoading, error } = useIndex();
  if (isLoading) return <Loading />;
  if (error) return <ErrorNotice error={error} />;
  const entry = data!.apps.find((a) => a.app_label === app);
  if (!entry) return <Empty title="Page not found">There is no application called “{app}”.</Empty>;
  return (
    <>
      <Crumbs items={[{ label: entry.name }]} />
      <PageHeader title={`${entry.name} administration`} />
      <AppPanel app={entry} />
    </>
  );
}
