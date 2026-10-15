/**
 * Old page URLs (/documents/..., /library/...) -> their place under the dashboard they belong to:
 * Content Lab Management pages live under /content-lab-management/, Journal Selector pages under
 * /journal-selector/. Keeps bookmarks, emailed links and stored notification links working.
 * Pages moved to the superadmin and the legal pages keep their old URLs (they have their own routes).
 */
const CL = '/content-lab-management';
const JS = '/journal-selector';

const RULES: [RegExp, string][] = [
  [/^\/documents\/(dashboard-selection\/)?$/, '/home'],
  [/^\/documents\/(content-lab|home|list|user-home|teacher-home|manager-dashboard)\//, `${CL}/dashboard/`],
  [/^\/documents\/other-documents\/profile\//, `${JS}/profile/`],
  [/^\/documents\/other-documents\//, `${JS}/dashboard/`],
  [/^\/documents\/journal-selector\//, `${JS}/journals/`],
  [/^\/documents\/(projects|collaborators|all-collaborators-projects|conference-selector|analytics|export-data)\//, `${JS}/$1/`],
  [/^\/documents\//, `${CL}/`],
  [/^\/library\/$/, `${CL}/library/`],
  [/^\/library\/references\//, `${CL}/reference-library/`],
  [/^\/library\//, `${CL}/`],
];

export function legacyToNewPath(pathname: string): string | null {
  const path = pathname.endsWith('/') ? pathname : `${pathname}/`;
  for (const [pattern, replacement] of RULES) {
    if (pattern.test(path)) return path.replace(pattern, replacement);
  }
  return null;
}
