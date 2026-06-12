'use client';

import { useState, useCallback } from 'react';
import { useWatchlistContext } from '../contexts/WatchlistContext';

/**
 * Per-symbol watchlist hook — thin wrapper around WatchlistContext that
 * exposes the star-button API used by the analysis page.
 *
 * `currentSymbol` is optional; when provided, `currentIsSaved` reflects
 * whether that ticker is currently in the watchlist.
 */
export function useWatchlist(currentSymbol?: string) {
  const { watchlist, isLoading, isWatched, add, remove } = useWatchlistContext();
  const [toggling, setToggling] = useState(false);

  const toggle = useCallback(async (symbol: string) => {
    setToggling(true);
    try {
      if (isWatched(symbol)) {
        await remove(symbol);
      } else {
        await add(symbol);
      }
    } finally {
      setToggling(false);
    }
  }, [isWatched, add, remove]);

  return {
    /** Full WatchlistItem list (id, symbol, added_at). */
    watchlist,
    /** True while the initial list is loading. */
    loading: isLoading,
    /** True while an add/remove is in-flight for the toggled symbol. */
    toggling,
    /** Returns true when the given symbol is in the watchlist. */
    isSaved: isWatched,
    /** Toggle add/remove for the given symbol. */
    toggle,
    /** Whether the `currentSymbol` prop is currently saved. */
    currentIsSaved: currentSymbol ? isWatched(currentSymbol) : false,
  };
}
