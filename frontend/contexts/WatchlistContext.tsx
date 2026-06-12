'use client';

import {
  createContext, useContext, useEffect, useState, useCallback, ReactNode,
} from 'react';
import type { WatchlistItem } from '../types';
import { useAuth } from './AuthContext';

interface WatchlistContextValue {
  watchlist:  WatchlistItem[];
  isLoading:  boolean;
  isWatched:  (symbol: string) => boolean;
  add:        (symbol: string) => Promise<void>;
  remove:     (symbol: string) => Promise<void>;
  reload:     () => Promise<void>;
}

const WatchlistContext = createContext<WatchlistContextValue>({
  watchlist: [], isLoading: false,
  isWatched: () => false,
  add: async () => {},
  remove: async () => {},
  reload: async () => {},
});

function authHeader(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const { session }                       = useAuth();
  const [watchlist,  setWatchlist]        = useState<WatchlistItem[]>([]);
  const [isLoading,  setIsLoading]        = useState(false);

  const token = session?.access_token ?? '';

  const reload = useCallback(async () => {
    if (!token) { setWatchlist([]); return; }
    setIsLoading(true);
    try {
      const res  = await fetch('/api/watchlist', { headers: authHeader(token) });
      const data = await res.json() as { watchlist?: WatchlistItem[] };
      setWatchlist(data.watchlist ?? []);
    } catch {
      // non-fatal — watchlist silently unavailable
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  // Reload on auth-state change (login / logout / token refresh)
  useEffect(() => { void reload(); }, [reload]);

  const isWatched = (symbol: string) =>
    watchlist.some(w => w.symbol.toUpperCase() === symbol.toUpperCase());

  const add = async (symbol: string) => {
    if (!token) return;
    const sym = symbol.toUpperCase();
    // Optimistic update
    if (!isWatched(sym)) {
      setWatchlist(prev => [{ id: 'optimistic', symbol: sym, added_at: new Date().toISOString() }, ...prev]);
    }
    try {
      await fetch('/api/watchlist', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader(token) },
        body:    JSON.stringify({ symbol: sym }),
      });
    } catch { /* non-fatal */ }
    // Re-sync to get the real id
    await reload();
  };

  const remove = async (symbol: string) => {
    if (!token) return;
    const sym = symbol.toUpperCase();
    // Optimistic update
    setWatchlist(prev => prev.filter(w => w.symbol !== sym));
    try {
      await fetch(`/api/watchlist/${encodeURIComponent(sym)}`, {
        method:  'DELETE',
        headers: authHeader(token),
      });
    } catch { /* non-fatal */ }
    await reload();
  };

  return (
    <WatchlistContext.Provider value={{ watchlist, isLoading, isWatched, add, remove, reload }}>
      {children}
    </WatchlistContext.Provider>
  );
}

export const useWatchlistContext = () => useContext(WatchlistContext);
