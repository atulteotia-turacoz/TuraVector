import type { ReactNode } from 'react';

/**
 * A page route contributed by a feature folder.
 *
 * Every `src/features/<name>/routes.tsx` must `export const routes: AppRoute[]`.
 * App.tsx collects them automatically — no central file to edit.
 *
 * Paths keep the original Django URLs (e.g. `/content-lab-management/document/:documentId/`)
 * so bookmarks and emailed links continue to work.
 */
export interface AppRoute {
  path: string;
  element: ReactNode;
  /** main = base.html sidebar, other = other_documents_base.html, bare = full-screen (viewers, auth pages) */
  layout: 'main' | 'other' | 'bare';
  /** true = reachable without login (login, signup, forgot password, legal pages) */
  public?: boolean;
}
