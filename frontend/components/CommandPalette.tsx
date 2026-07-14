'use client';

/**
 * Command Palette (Feature 33) — global Ctrl/Cmd+K (and "/") launcher.
 *
 * One instance is rendered by the (app) layout; it self-manages open state.
 * Three result groups share a single keyboard-navigable listbox:
 *   Tickers — fuzzy match over the shared TICKER_UNIVERSE → /analysis?symbol=
 *   Pages   — the same NAV_ITEMS the sidebar renders
 *   Actions — theme toggle, quick-jumps, random ticker
 * Empty query shows Recent tickers (localStorage `fiforesight:palette:recent`)
 * + Pages + Actions. Other UI (sidebar / mobile nav buttons) opens it via
 * `openCommandPalette()` — a window CustomEvent, no prop threading.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Box, Chip, Dialog, InputBase, Typography, useMediaQuery, useTheme,
} from '@mui/material';
import {
  Search, Star, Wallet, Bell, SlidersHorizontal, Sun, Moon, Dices,
  TrendingUp, History, CornerDownLeft,
} from 'lucide-react';
import { NAV_ITEMS } from '../lib/navItems';
import { TICKER_UNIVERSE, searchTickers, randomTicker, type TickerEntry } from '../lib/tickerSearch';
import { matchTier } from '../lib/fuzzy';
import { useAppShell } from '../contexts/AppShellContext';
import { useAuth } from '../contexts/AuthContext';
import { useWatchlistContext } from '../contexts/WatchlistContext';

export const PALETTE_OPEN_EVENT = 'fiforesight:palette:open';
const RECENT_KEY = 'fiforesight:palette:recent';
const MAX_RECENT = 5;

/** Open the palette from anywhere (sidebar / mobile nav buttons). */
export function openCommandPalette() {
  window.dispatchEvent(new Event(PALETTE_OPEN_EVENT));
}

/** Small bordered keycap, e.g. <Kbd>⌘K</Kbd>. */
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <Box
      component="kbd"
      sx={{
        px: 0.75, py: 0.1, fontSize: 10, fontWeight: 700, fontFamily: 'inherit',
        lineHeight: 1.7, color: 'text.secondary', whiteSpace: 'nowrap',
        border: '1px solid', borderColor: 'divider', borderBottomWidth: 2,
        borderRadius: 1, bgcolor: 'transparent',
      }}
    >
      {children}
    </Box>
  );
}

type IconType = React.ComponentType<{ size?: number | string; color?: string }>;

interface PaletteItem {
  id:        string;
  group:     'Recent' | 'Tickers' | 'Pages' | 'Actions';
  label:     string;
  sublabel?: string;
  hint?:     string;
  icon:      IconType;
  /** Set on ticker rows — enables the watchlist affordance. */
  symbol?:   string;
  run:       () => void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

function loadRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const arr = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(arr) ? arr.filter((s): s is string => typeof s === 'string').slice(0, MAX_RECENT) : [];
  } catch { return []; }
}

function pushRecent(symbol: string): string[] {
  const next = [symbol, ...loadRecent().filter(s => s !== symbol)].slice(0, MAX_RECENT);
  try { window.localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* non-fatal */ }
  return next;
}

export default function CommandPalette() {
  const router   = useRouter();
  const theme    = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const { isDark, primaryColor, toggleTheme } = useAppShell();
  const { user } = useAuth();
  const { isWatched, add, remove } = useWatchlistContext();

  const [open,        setOpen]        = useState(false);
  const [query,       setQuery]       = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [recent,      setRecent]      = useState<string[]>([]);
  const listRef = useRef<HTMLUListElement>(null);

  const close = useCallback(() => setOpen(false), []);

  const openPalette = useCallback(() => {
    setQuery('');
    setActiveIndex(0);
    setRecent(loadRecent());
    setOpen(true);
  }, []);

  // Global shortcuts: Ctrl/Cmd+K toggles (always, even from inputs);
  // "/" opens only when no editable element has focus.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(prev => {
          if (prev) return false;
          // openPalette resets state; do it inline since we're in a reducer
          setQuery(''); setActiveIndex(0); setRecent(loadRecent());
          return true;
        });
        return;
      }
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !isEditableTarget(e.target)) {
        e.preventDefault();
        openPalette();
      }
    };
    const onOpenEvent = () => openPalette();
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener(PALETTE_OPEN_EVENT, onOpenEvent);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener(PALETTE_OPEN_EVENT, onOpenEvent);
    };
  }, [openPalette]);

  const selectTicker = useCallback((symbol: string) => {
    setRecent(pushRecent(symbol));
    setOpen(false);
    router.push(`/analysis?symbol=${encodeURIComponent(symbol)}`);
  }, [router]);

  const navigateTo = useCallback((href: string) => {
    setOpen(false);
    router.push(href);
  }, [router]);

  // ── Build the flattened, filtered item list ──────────────────────────────
  const items = useMemo<PaletteItem[]>(() => {
    const q = query.trim();
    const out: PaletteItem[] = [];

    const tickerItem = (t: TickerEntry, group: 'Recent' | 'Tickers'): PaletteItem => ({
      id: `${group.toLowerCase()}-${t.symbol}`,
      group,
      label: t.symbol,
      sublabel: t.name,
      hint: 'Analyze',
      icon: group === 'Recent' ? History : TrendingUp,
      symbol: t.symbol,
      run: () => selectTicker(t.symbol),
    });

    if (q) {
      for (const t of searchTickers(q, 8)) out.push(tickerItem(t, 'Tickers'));
    } else {
      for (const sym of recent) {
        const known = TICKER_UNIVERSE.find(t => t.symbol === sym);
        out.push(tickerItem(known ?? { symbol: sym, name: '' }, 'Recent'));
      }
    }

    for (const { label, href, icon } of NAV_ITEMS) {
      if (q && matchTier(q, label) === 0) continue;
      out.push({
        id: `page-${href}`, group: 'Pages', label, icon,
        hint: 'Jump to', run: () => navigateTo(href),
      });
    }

    const actions: Array<Omit<PaletteItem, 'group'> & { keywords: string }> = [
      {
        id: 'action-theme',
        label: isDark ? 'Switch to light theme' : 'Switch to dark theme',
        keywords: 'toggle theme dark light mode appearance',
        icon: isDark ? Sun : Moon,
        run: () => { toggleTheme(); close(); },
      },
      { id: 'action-watchlist', label: 'Go to my Watchlist', keywords: 'go my watchlist saved stars',
        icon: Star, run: () => navigateTo('/watchlist') },
      { id: 'action-portfolio', label: 'Go to my Portfolio', keywords: 'go my portfolio holdings pnl',
        icon: Wallet, run: () => navigateTo('/portfolio') },
      { id: 'action-alerts', label: 'Go to my Alerts', keywords: 'go my alerts notifications rules',
        icon: Bell, run: () => navigateTo('/alerts') },
      { id: 'action-screener', label: 'Open Screener', keywords: 'open equity screener filter scan',
        icon: SlidersHorizontal, run: () => navigateTo('/screener') },
      { id: 'action-random', label: 'Random ticker', sublabel: 'Feeling lucky?',
        keywords: 'random ticker surprise lucky dice',
        icon: Dices, run: () => selectTicker(randomTicker().symbol) },
    ];
    for (const { keywords, ...a } of actions) {
      if (q && matchTier(q, a.label) === 0 && matchTier(q, keywords) === 0) continue;
      out.push({ ...a, group: 'Actions' });
    }

    return out;
  }, [query, recent, isDark, toggleTheme, close, selectTicker, navigateTo]);

  // Clamp at render time — the list can shrink while open (typing, watchlist
  // changes) and a stale index must never point past the end.
  const safeIndex = items.length ? Math.min(activeIndex, items.length - 1) : 0;

  // Keep the highlighted row visible.
  useEffect(() => {
    listRef.current
      ?.querySelector(`#palette-opt-${safeIndex}`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [safeIndex]);

  const onInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (items.length) setActiveIndex((safeIndex + 1) % items.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (items.length) setActiveIndex((safeIndex - 1 + items.length) % items.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      items[safeIndex]?.run();
    }
  };

  // ── Styling (glassy, matches StockChatPanel) ─────────────────────────────
  const bgPaper   = isDark ? 'rgba(5,10,16,0.97)' : 'rgba(248,250,252,0.97)';
  const borderCol = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const dimColor  = isDark ? 'rgba(220,220,220,0.4)' : 'rgba(20,30,50,0.45)';
  const activeId  = items.length ? `palette-opt-${safeIndex}` : undefined;

  let lastGroup: PaletteItem['group'] | null = null;

  return (
    <Dialog
      open={open}
      onClose={close}
      fullWidth
      maxWidth={false}
      aria-label="Command palette"
      sx={{ '& .MuiDialog-container': { alignItems: 'flex-start' } }}
      slotProps={{
        paper: {
          'data-testid': 'command-palette',
          sx: {
            background: bgPaper,
            backdropFilter: 'blur(20px)',
            border: `1px solid ${primaryColor}22`,
            borderRadius: isMobile ? '0 0 16px 16px' : 4,
            width: isMobile ? '100%' : 560,
            maxWidth: isMobile ? '100%' : '90vw',
            m: isMobile ? 0 : undefined,
            mt: isMobile ? 0 : '12vh',
            overflow: 'hidden',
          },
        } as object,
      }}
    >
      {/* Input row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 2, py: isMobile ? 1.75 : 1.25,
                 borderBottom: `1px solid ${borderCol}` }}>
        <Search size={isMobile ? 20 : 18} color={primaryColor} style={{ flexShrink: 0 }} />
        <InputBase
          autoFocus
          fullWidth
          placeholder="Search tickers, pages, actions…"
          value={query}
          onChange={e => { setQuery(e.target.value); setActiveIndex(0); }}
          onKeyDown={onInputKeyDown}
          inputProps={{
            'data-testid': 'palette-input',
            role: 'combobox',
            'aria-expanded': true,
            'aria-controls': 'palette-listbox',
            'aria-activedescendant': activeId,
            'aria-autocomplete': 'list',
          }}
          sx={{ fontSize: isMobile ? 17 : 15, fontWeight: 600 }}
        />
        {!isMobile && <Kbd>Esc</Kbd>}
      </Box>

      {/* Results */}
      <Box
        component="ul"
        ref={listRef}
        role="listbox"
        id="palette-listbox"
        aria-label="Palette results"
        sx={{ m: 0, p: 1, listStyle: 'none', overflowY: 'auto', overflowX: 'hidden',
              maxHeight: isMobile ? 'calc(100dvh - 180px)' : '55vh' }}
      >
        {items.length === 0 && (
          <Typography sx={{ px: 1.5, py: 3, fontSize: 13, color: dimColor, textAlign: 'center' }}>
            No matches for &ldquo;{query.trim()}&rdquo;
          </Typography>
        )}

        {items.map((item, i) => {
          const header = item.group !== lastGroup ? item.group : null;
          lastGroup = item.group;
          const active = i === safeIndex;
          const Icon = item.icon;
          const watched = item.symbol ? isWatched(item.symbol) : false;

          return (
            <Box component="span" key={item.id} sx={{ display: 'block' }}>
              {header && (
                <Typography
                  component="div"
                  role="presentation"
                  sx={{ px: 1.5, pt: i === 0 ? 0.5 : 1.5, pb: 0.5, fontSize: 10, fontWeight: 700,
                        letterSpacing: 1, textTransform: 'uppercase', color: dimColor }}
                >
                  {header === 'Recent' ? 'Recent tickers' : header}
                </Typography>
              )}
              <Box
                component="li"
                id={`palette-opt-${i}`}
                role="option"
                aria-selected={active}
                onClick={item.run}
                onMouseEnter={() => setActiveIndex(i)}
                sx={{
                  display: 'flex', alignItems: 'center', gap: 1.5,
                  px: 1.5, py: isMobile ? 1.4 : 1, borderRadius: 2, cursor: 'pointer',
                  minHeight: isMobile ? 48 : undefined,
                  bgcolor: active ? `${primaryColor}22` : 'transparent',
                  transition: 'background 0.1s ease',
                }}
              >
                <Icon size={17} color={active ? primaryColor : dimColor} />
                <Box sx={{ minWidth: 0, flexGrow: 1, display: 'flex', alignItems: 'baseline', gap: 1 }}>
                  <Typography sx={{ fontSize: 13.5, fontWeight: 650, color: 'text.primary', whiteSpace: 'nowrap' }}>
                    {item.label}
                  </Typography>
                  {item.sublabel && (
                    <Typography sx={{ fontSize: 11.5, color: dimColor, overflow: 'hidden',
                                      textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.sublabel}
                    </Typography>
                  )}
                </Box>

                {/* Watchlist affordance on ticker rows (signed-in only) */}
                {item.symbol && user && (
                  <Chip
                    size="small"
                    label={watched ? 'Remove' : '+ Watchlist'}
                    onClick={(e) => {
                      e.stopPropagation();
                      void (watched ? remove(item.symbol as string) : add(item.symbol as string));
                    }}
                    sx={{
                      height: 22, fontSize: 10.5, fontWeight: 700, flexShrink: 0,
                      color: watched ? dimColor : primaryColor,
                      bgcolor: 'transparent',
                      border: `1px solid ${watched ? borderCol : `${primaryColor}55`}`,
                      '&:hover': { bgcolor: `${primaryColor}18` },
                    }}
                  />
                )}

                {item.hint && !isMobile && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0,
                             opacity: active ? 1 : 0.45 }}>
                    <Typography sx={{ fontSize: 10.5, color: dimColor }}>{item.hint}</Typography>
                    {active && <CornerDownLeft size={11} color={dimColor} />}
                  </Box>
                )}
              </Box>
            </Box>
          );
        })}
      </Box>

      {/* Footer hints (desktop only) */}
      {!isMobile && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 2, py: 0.9,
                   borderTop: `1px solid ${borderCol}` }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Kbd>↑</Kbd><Kbd>↓</Kbd>
            <Typography sx={{ fontSize: 10.5, color: dimColor, ml: 0.25 }}>navigate</Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Kbd>↵</Kbd>
            <Typography sx={{ fontSize: 10.5, color: dimColor, ml: 0.25 }}>select</Typography>
          </Box>
          <Box sx={{ flexGrow: 1 }} />
          <Typography sx={{ fontSize: 10.5, color: dimColor }}>FiForesight</Typography>
        </Box>
      )}
    </Dialog>
  );
}
