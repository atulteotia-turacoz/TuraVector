import { Link } from 'react-router-dom';
import { Empty } from '@/components/ui';

export default function NotFound() {
  return <Empty title="Page not found" action={<Link className="btn btn-secondary" to="/">Back to site administration</Link>}>We’re sorry, but the requested page could not be found.</Empty>;
}
