import { useState, type FormEvent, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Book, Bookmark, Check, ExternalLink, Search } from 'lucide-react';
import { api, errorMessage } from '@/lib/api';
import { Badge, Empty, ErrorNotice, Loading, PageHeader, Panel, Spinner } from '@/components/ui';
import type { JournalResult, JournalSearchResponse, SavedJournal } from './api';
import './tools.css';

const SOURCE_LABEL: Record<string, string> = { springer_api: 'Springer', elsevier_api: 'Elsevier', pubmed_api: 'PubMed' };

function SaveButton({ journalId, initial }: { journalId: number; initial: boolean }) {
  const [saved, setSaved] = useState(initial);
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    const action = saved ? 'unsave' : 'save';
    setBusy(true);
    try {
      await api.post('/api/tools/save-journal', { journal_id: journalId, action });
      setSaved(action === 'save');
    } catch (err) {
      window.alert(errorMessage(err, 'An error occurred. Please try again.'));
    } finally { setBusy(false); }
  };
  return (
    <button className={`btn btn-sm ${saved ? 'btn-primary' : 'btn-secondary'}`} disabled={busy} onClick={toggle}>
      {busy ? <Spinner /> : saved ? <Check size={13} /> : <Bookmark size={13} />} {saved ? 'Saved' : 'Save'}
    </button>
  );
}

function Title({ name, submissionUrl, websiteUrl, extra }: { name: string; submissionUrl?: string | null; websiteUrl?: string | null; extra?: ReactNode }) {
  return (
    <h3>
      {submissionUrl ? (
        <><a href={submissionUrl} target="_blank" rel="noreferrer" title="View submission guidelines" className="row-tight">{name} <ExternalLink size={12} /></a>
          <Badge tone="ok">Submission Guide</Badge></>
      ) : websiteUrl ? (
        <a href={websiteUrl} target="_blank" rel="noreferrer" title="Visit journal website" className="row-tight">{name} <ExternalLink size={12} /></a>
      ) : name}
      {extra}
    </h3>
  );
}

function Cover({ url, name }: { url: string | null; name: string }) {
  return <div className="tools-journal-cover">{url ? <img src={url} alt={name} /> : <Book size={22} />}</div>;
}

function Metric({ label, children }: { label: string; children: ReactNode }) {
  return <div><div className="tiny">{label}</div><div className="small">{children}</div></div>;
}

function ResultCard({ j }: { j: JournalResult }) {
  return (
    <div className="tools-journal">
      <Cover url={j.cover_image_url} name={j.name} />
      <div className="grow">
        <Title name={j.name} submissionUrl={j.submission_url} websiteUrl={j.website_url}
          extra={<Badge tone={j.source === 'local' ? undefined : 'accent'}>{SOURCE_LABEL[j.source] || 'Local'}</Badge>} />
        {j.publisher && <p className="small muted">{j.publisher}</p>}
        <div className="tools-metrics">
          <Metric label="Publishing Model">{j.publishing_model}</Metric>
          <Metric label="Impact Factor">{j.impact_factor} {j.impact_factor_year ? `(${j.impact_factor_year})` : ''}</Metric>
          <Metric label="Downloads">{j.downloads.toLocaleString()}</Metric>
          <Metric label="Submission to Decision">{j.submission_days !== 'N/A' ? `${j.submission_days} days` : 'N/A'}</Metric>
        </div>
        {(j.primary_subject || j.secondary_subjects.length > 0) && (
          <div className="tools-tags">
            {j.primary_subject && <span className="badge">{j.primary_subject}</span>}
            {j.secondary_subjects.map((s, i) => <span key={i} className="badge">{s}</span>)}
          </div>
        )}
        <SaveButton journalId={j.id} initial={j.is_saved} />
      </div>
    </div>
  );
}

/** documents/journal_selector.html */
export default function JournalSelectorPage() {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<JournalSearchResponse | null>(null);
  const saved = useQuery({
    queryKey: ['tools', 'journal-selector'],
    queryFn: async () => (await api.get<{ user_selections: SavedJournal[]; saved_journals_count: number }>('/api/tools/journal-selector')).data,
    refetchOnWindowFocus: false,
  });

  const search = async (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setResults(null);
    try {
      const { data } = await api.post<JournalSearchResponse>('/api/tools/journal-search', { query: q });
      setResults(data);
      if (data.warning) console.warn(data.warning);
    } catch (err) {
      window.alert(errorMessage(err, 'An error occurred while searching. Please try again.'));
    } finally { setSearching(false); }
  };

  let countText = '';
  if (results) {
    countText = `${results.count} journals found`;
    const s = results.sources;
    if (s) {
      const parts: string[] = [];
      if ((s.local_count ?? 0) > 0) parts.push(`${s.local_count} local`);
      if ((s.springer_api_count ?? 0) > 0) parts.push(`${s.springer_api_count} from Springer`);
      if ((s.elsevier_api_count ?? 0) > 0) parts.push(`${s.elsevier_api_count} from Elsevier`);
      if ((s.pubmed_api_count ?? 0) > 0) parts.push(`${s.pubmed_api_count} from PubMed`);
      if (parts.length) countText += ` (${parts.join(', ')})`;
    }
  }

  return (
    <div className="stack-lg">
      <PageHeader title="Journal Selector" />
      <Panel title="Find Journals for Your Research">
        <p className="muted" style={{ marginBottom: 12 }}>Search by manuscript title, abstract, or keywords to find relevant journals</p>
        <form className="row" onSubmit={search}>
          <input className="input grow" required value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter manuscript title, abstract, or keywords..." />
          <button type="submit" className="btn btn-primary" disabled={searching}><Search size={14} /> Search</button>
        </form>
      </Panel>

      {searching && <div className="empty"><Spinner label="Searching for journals..." /></div>}

      {results && (
        <Panel title="Search Results" actions={<span className="small muted">{countText}</span>}>
          {results.journals.length === 0 ? (
            <Empty title="No journals found matching your search.">Try different keywords or broaden your search criteria.</Empty>
          ) : results.journals.map((j) => <ResultCard key={j.id} j={j} />)}
        </Panel>
      )}

      {saved.isLoading ? <Loading /> : saved.error ? <ErrorNotice error={saved.error} /> : (
        <Panel title={`My Saved Journals (${saved.data!.saved_journals_count})`}>
          {saved.data!.user_selections.length === 0 ? (
            <Empty title="You haven't saved any journals yet.">Search for journals above and save the ones relevant to your research.</Empty>
          ) : saved.data!.user_selections.map((s) => (
            <div key={s.id} className="tools-journal">
              <Cover url={s.journal.cover_image_url} name={s.journal.name} />
              <div className="grow">
                <Title name={s.journal.name} submissionUrl={s.journal.submission_url} websiteUrl={s.journal.website_url} />
                {s.journal.publisher && <p className="small muted">{s.journal.publisher}</p>}
                <div className="tools-metrics">
                  <Metric label="Publishing Model">{s.journal.publishing_model}</Metric>
                  <Metric label="Impact Factor">
                    {s.journal.impact_factor ? `${s.journal.impact_factor}${s.journal.impact_factor_year ? ` (${s.journal.impact_factor_year})` : ''}` : 'N/A'}
                  </Metric>
                  <Metric label="Submission to Decision">
                    {s.journal.submission_to_decision_days ? `${s.journal.submission_to_decision_days} days` : 'N/A'}
                  </Metric>
                </div>
                {s.manuscript_title && <div className="small" style={{ marginBottom: 10 }}><strong>Manuscript:</strong> {s.manuscript_title}</div>}
                <div className="row">
                  <SaveButton journalId={s.journal.id} initial />
                  {s.journal.website_url && (
                    <a className="btn btn-secondary btn-sm" href={s.journal.website_url} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Visit Website</a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </Panel>
      )}
    </div>
  );
}
