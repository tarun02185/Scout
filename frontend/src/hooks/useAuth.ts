import { useState, useEffect, useCallback } from 'react';
import { googleLogin, guestLogin, getMe, type User } from '../services/api';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = localStorage.getItem('auth_token');
    if (t) {
      getMe().then((u) => { setUser(u); setLoading(false); })
        .catch(() => { localStorage.removeItem('auth_token'); setLoading(false); });
    } else setLoading(false);
  }, []);

  const login = useCallback(async (credential: string) => {
    try { const r = await googleLogin(credential); localStorage.setItem('auth_token', r.token); setUser(r.user); return true; }
    catch { return false; }
  }, []);

  const loginGuest = useCallback(async () => {
    try { const r = await guestLogin(); localStorage.setItem('auth_token', r.token); setUser(r.user); return true; }
    catch { return false; }
  }, []);

  const logout = useCallback(() => { localStorage.removeItem('auth_token'); setUser(null); }, []);

  return { user, loading, login, loginGuest, logout };
}
