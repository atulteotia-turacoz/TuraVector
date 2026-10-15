import { Link } from 'react-router-dom';
import { adminPath, type DeleteNode, type DeleteSummary } from '@/lib/admin';

function Tree({ nodes }: { nodes: DeleteNode[] }) {
  return (
    <ul>
      {nodes.map((n, i) => (
        <li key={i}>
          <span className="model">{n.model}: </span>
          {n.link ? <Link className="act" to={adminPath(n.link)}>{n.str}</Link> : <span>{n.str}</span>}
          {n.children.length > 0 && <Tree nodes={n.children} />}
        </li>
      ))}
    </ul>
  );
}

/** Body of Django's delete_confirmation / delete_selected_confirmation templates. */
export function DeleteSummaryView({ summary, intro, protectedIntro }: { summary: DeleteSummary; intro: string; protectedIntro: string }) {
  if (summary.protected.length) {
    return (
      <div className="stack">
        <div className="notice notice-danger">{protectedIntro}</div>
        <ul className="del-tree">
          {summary.protected.map((p, i) => (
            <li key={i}><span className="model">{p.model}: </span>{p.link ? <Link className="act" to={adminPath(p.link)}>{p.str}</Link> : p.str}</li>
          ))}
        </ul>
      </div>
    );
  }
  return (
    <div className="stack">
      <p>{intro}</p>
      <div>
        <h3 className="section-title" style={{ marginTop: 6 }}>Summary</h3>
        <ul className="del-tree">
          {summary.counts.map((c) => <li key={c.model}><span className="model">{c.model}:</span> {c.count}</li>)}
        </ul>
      </div>
      <div>
        <h3 className="section-title" style={{ marginTop: 6 }}>Objects</h3>
        <div className="del-tree"><Tree nodes={summary.objects} /></div>
        {summary.truncated && <p className="small muted" style={{ marginTop: 8 }}>The list was shortened for display; every object counted in the summary will be deleted.</p>}
      </div>
    </div>
  );
}
