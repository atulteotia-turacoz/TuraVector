import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, getToken, setToken } from './api';

/** Subset of GET /api/auth/me used by the admin. */
export interface Me {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  timezone: string;
  is_staff: boolean;
  is_superuser: boolean;
  is_active: boolean;
}

interface AuthValue {
  user: Me | null;
  loading: boolean;
  login: (username: string, password: string, privacy_consent: boolean) => Promise<Me>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getToken());
  const qc = useQueryClient();

  const refresh = useCallback(async () => {
    if (!getToken()) { setUser(null); setLoading(false); return; }
    try {
      const { data } = await api.get<Me>('/api/auth/me');
      setUser(data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const login = useCallback(async (username: string, password: string, privacy_consent: boolean) => {
    const { data } = await api.post('/api/auth/login', { username, password, privacy_consent });
    setToken(data.access_token);
    setUser(data.user);
    return data.user as Me;
  }, []);

  const logout = useCallback(async () => {
    try { await api.post('/api/auth/logout'); } catch { /* token may already be invalid */ }
    setToken(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  const value = useMemo(() => ({ user, loading, login, logout, refresh }), [user, loading, login, logout, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

export function useUser(): Me {
  const { user } = useAuth();
  if (!user) throw new Error('useUser called outside an authenticated route');
  return user;
}
