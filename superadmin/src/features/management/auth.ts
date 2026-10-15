/**
 * Adapter so the management pages moved from the user app keep their `useAuth()` checks.
 * Only superusers can open the superadmin, and a superuser passes every manager check.
 */
import { useAuth as useAdminAuth } from '@/lib/auth';

export function useAuth() {
  const { user, ...rest } = useAdminAuth();
  return { ...rest, user: user ? { ...user, is_manager_like: true } : null };
}
