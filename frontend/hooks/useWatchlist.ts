'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { fetchWatchlist, addToWatchlist, removeFromWatchlist } from '../lib/watchlist';

export function useWatchlist(currentSymbol?: string) {
  const { user } = useAuth();
  const [watchlist, setWatchlist]   = useState<string[]>([]);
  const [loading, setLoading]       = useState(false);
  const [toggling, setToggling]     = useState(false);

  const load = useCallback(async () => {
    if (!user) { setWatchlist([]); return; }
    setLoading(true);
    try {
      setWatchlist(await fetchWatchlist(user.id));
    } catch {
      // non-fatal — watchlist feature silently unavailable if table not set up
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { void load(); }, [load]);

  const isSaved = (symbol: string) =>
    watchlist.includes(symbol.toUpperCase());

  async function toggle(symbol: string) {
    if (!user) return;
    const sym = symbol.toUpperCase();
    setToggling(true);
    try {
      if (isSaved(sym)) {
        await removeFromWatchlist(user.id, sym);
        setWatchlist(prev => prev.filter(s => s !== sym));
      } else {
        await addToWatchlist(user.id, sym);
        setWatchlist(prev => [sym, ...prev]);
      }
    } catch {
      // non-fatal
    } finally {
      setToggling(false);
    }
  }

  return {
    watchlist,
    loading,
    toggling,
    isSaved,
    toggle,
    currentIsSaved: currentSymbol ? isSaved(currentSymbol) : false,
  };
}
