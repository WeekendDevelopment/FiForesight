'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import {
  Box, Button, Drawer, List, ListItemButton, ListItemIcon, ListItemText,
  Stack, Typography, IconButton, Tooltip, useMediaQuery,
} from '@mui/material';
import {
  BrainCircuit, Search, ChevronLeft, ChevronRight, Sun, Moon, LogIn, LogOut,
  Star, ChevronDown, ChevronUp, MoreHorizontal,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { AppShellProvider, useAppShell } from '../../contexts/AppShellContext';
import { useAuth } from '../../contexts/AuthContext';
import { useWatchlistContext } from '../../contexts/WatchlistContext';
import AuthModal from '../../components/AuthModal';
import CommandPalette, { openCommandPalette } from '../../components/CommandPalette';
// Navigation model lives in lib/navItems.ts (shared with the command palette,
// Feature 33) — add/remove routes THERE, not here.
import { NAV_ITEMS } from '../../lib/navItems';

const EXPANDED_WIDTH  = 220;
const COLLAPSED_WIDTH = 64;
const COLLAPSE_KEY    = 'sidebar_collapsed';

// Active when the path matches exactly, or (for non-root items) is nested under it.
function isActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}

// ── Desktop sidebar ─────────────────────────────────────────────────────────
function WatchlistPanel({ collapsed, isDark, primaryColor }: { collapsed: boolean; isDark: boolean; primaryColor: string }) {
  const router = useRouter();
  const { watchlist, isLoading } = useWatchlistContext();
  const [open, setOpen] = useState(true);

  const dimColor  = isDark ? 'rgba(220,220,220,0.35)' : 'rgba(20,30,50,0.35)';
  const hoverBg   = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';
  const borderCol = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';

  if (collapsed) {
    // In collapsed mode show just the star icon (no panel)
    return (
      <Tooltip title="Watchlist" placement="right">
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 1 }}>
          <Star size={18} color={dimColor} />
        </Box>
      </Tooltip>
    );
  }

  return (
    <Box sx={{ px: 1, mt: 0.5, borderTop: `1px solid ${borderCol}`, pt: 1 }}>
      {/* Header row */}
      <Box
        onClick={() => setOpen(p => !p)}
        sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              px: 1.5, py: 0.75, borderRadius: 2, cursor: 'pointer',
              '&:hover': { bgcolor: hoverBg } }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Star size={14} color={primaryColor} />
          <Typography sx={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.8,
                            textTransform: 'uppercase', color: dimColor }}>
            Watchlist
          </Typography>
          {isLoading && <Typography sx={{ fontSize: 10, color: dimColor, opacity: 0.6 }}>…</Typography>}
        </Box>
        {open ? <ChevronUp size={12} color={dimColor} /> : <ChevronDown size={12} color={dimColor} />}
      </Box>

      {open && (
        <Box sx={{ mt: 0.5 }}>
          {watchlist.length === 0 ? (
            <Typography sx={{ fontSize: 11, color: dimColor, px: 1.5, py: 0.5, opacity: 0.7 }}>
              Star a ticker to save it here.
            </Typography>
          ) : (
            watchlist.slice(0, 12).map(item => (
              <Box
                key={item.id}
                onClick={() => router.push(`/analysis?symbol=${encodeURIComponent(item.symbol)}`)}
                sx={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  px: 1.5, py: 0.6, borderRadius: 1.5, cursor: 'pointer',
                  '&:hover': { bgcolor: hoverBg },
                }}
              >
                <Typography sx={{ fontSize: 12, fontWeight: 700, color: 'text.primary', lineHeight: 1.2 }}>
                  {item.symbol}
                </Typography>
              </Box>
            ))
          )}
        </Box>
      )}
    </Box>
  );
}

function Sidebar() {
  const pathname            = usePathname();
  const { isDark, primaryColor, themeMode, toggleTheme } = useAppShell();
  const { user, signOut }   = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [authOpen,  setAuthOpen]  = useState(false);

  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration of persisted pref
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === 'true');
    } catch { /* non-fatal */ }
  }, []);

  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev;
      try { window.localStorage.setItem(COLLAPSE_KEY, String(next)); } catch { /* non-fatal */ }
      return next;
    });
  };

  // Activate a click handler on Enter/Space for keyboard users (the footer
  // controls are styled Boxes rather than <button>s).
  const onActivate = (fn: () => void) => (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); }
  };

  const handleAuthClick = () => {
    if (user) {
      signOut().catch(err => console.error('Sign out failed:', err));
    } else {
      setAuthOpen(true);
    }
  };

  const width      = collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH;
  const borderCol  = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const hoverBg    = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';
  const activeBg   = `${primaryColor}1a`;

  return (
    <Box
      component="nav"
      sx={{
        width, flexShrink: 0,
        height: '100vh', position: 'sticky', top: 0,
        display: { xs: 'none', md: 'flex' }, flexDirection: 'column',
        borderRight: `1px solid ${borderCol}`,
        bgcolor: 'background.paper',
        transition: 'width 0.2s ease',
        maxWidth: 280,  // prevent sprawl at 4K
      }}
    >
      {/* Header */}
      <Box sx={{ px: collapsed ? 1.5 : 2.5, py: 2.5, display: 'flex', alignItems: 'center', gap: 1.25, minHeight: 64 }}>
        <BrainCircuit size={26} color={primaryColor} style={{ flexShrink: 0 }} />
        {!collapsed && (
          <Typography variant="h6" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
            FiForesight
          </Typography>
        )}
      </Box>

      {/* Nav items */}
      <Stack spacing={0.5} sx={{ px: 1, mt: 1, flexGrow: 1 }}>
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
          const active = isActive(pathname, href);
          const link = (
            <Box
              key={href}
              component={Link}
              href={href}
              sx={{
                display: 'flex', alignItems: 'center', gap: 1.5,
                px: 1.5, py: 1.1, borderRadius: 2,
                justifyContent: collapsed ? 'center' : 'flex-start',
                textDecoration: 'none',
                color: active ? primaryColor : 'text.secondary',
                bgcolor: active ? activeBg : 'transparent',
                fontWeight: active ? 700 : 500,
                transition: 'background 0.15s ease, color 0.15s ease',
                '&:hover': { bgcolor: active ? activeBg : hoverBg, color: active ? primaryColor : 'text.primary' },
              }}
            >
              <Icon size={20} color={active ? primaryColor : 'currentColor'} />
              {!collapsed && <Typography sx={{ fontSize: 14, fontWeight: 'inherit' }}>{label}</Typography>}
            </Box>
          );
          return collapsed
            ? <Tooltip key={href} title={label} placement="right">{link}</Tooltip>
            : link;
        })}
      </Stack>

      {/* Watchlist panel */}
      <WatchlistPanel collapsed={collapsed} isDark={isDark} primaryColor={primaryColor} />

      {/* Footer: theme toggle + auth + collapse */}
      <Stack spacing={0.5} sx={{ px: 1, py: 1.5, borderTop: `1px solid ${borderCol}` }}>
        {/* Theme toggle */}
        <Box
          onClick={toggleTheme}
          onKeyDown={onActivate(toggleTheme)}
          role="button"
          tabIndex={0}
          aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          sx={{
            display: 'flex', alignItems: 'center', gap: 1.5, cursor: 'pointer',
            px: 1.5, py: 1, borderRadius: 2, color: 'text.secondary',
            justifyContent: collapsed ? 'center' : 'flex-start',
            '&:hover': { bgcolor: hoverBg, color: 'text.primary' },
          }}
        >
          {isDark ? <Sun size={20} color={primaryColor} /> : <Moon size={20} color={primaryColor} />}
          {!collapsed && <Typography sx={{ fontSize: 14 }}>{themeMode === 'dark' ? 'Light mode' : 'Dark mode'}</Typography>}
        </Box>

        {/* Auth */}
        <Box
          onClick={handleAuthClick}
          onKeyDown={onActivate(handleAuthClick)}
          role="button"
          tabIndex={0}
          aria-label={user ? 'Sign out' : 'Sign in'}
          sx={{
            display: 'flex', alignItems: 'center', gap: 1.5, cursor: 'pointer',
            px: 1.5, py: 1, borderRadius: 2, color: 'text.secondary',
            justifyContent: collapsed ? 'center' : 'flex-start',
            '&:hover': { bgcolor: hoverBg, color: 'text.primary' },
          }}
        >
          {user ? <LogOut size={20} color={primaryColor} /> : <LogIn size={20} color={primaryColor} />}
          {!collapsed && (
            <Typography sx={{ fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user ? (user.email?.split('@')[0] ?? 'Sign out') : 'Sign In'}
            </Typography>
          )}
        </Box>
        <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />

        {/* Collapse toggle */}
        <Box sx={{ display: 'flex', justifyContent: collapsed ? 'center' : 'flex-end', px: 0.5, pt: 0.5 }}>
          <IconButton size="small" onClick={toggleCollapsed} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </IconButton>
        </Box>
      </Stack>
    </Box>
  );
}

// ── Mobile watchlist chip row (shown above bottom nav) ─────────────────────
function MobileWatchlistBar() {
  const router                   = useRouter();
  const { isDark, primaryColor } = useAppShell();
  const { watchlist }            = useWatchlistContext();
  const borderCol = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const chipBg    = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)';

  if (!watchlist.length) return null;

  return (
    <Box
      sx={{
        display: { xs: 'flex', md: 'none' },
        position: 'fixed', bottom: 60, left: 0, right: 0, zIndex: 1199,
        borderTop: `1px solid ${borderCol}`, bgcolor: 'background.paper',
        overflowX: 'auto', maxHeight: 48, alignItems: 'center',
        px: 1, gap: 0.75, flexShrink: 0,
        // Hide scrollbar but keep scrollability
        '&::-webkit-scrollbar': { display: 'none' },
        scrollbarWidth: 'none',
      }}
    >
      {watchlist.slice(0, 20).map(item => (
        <Box
          key={item.symbol}
          onClick={() => router.push(`/analysis?symbol=${encodeURIComponent(item.symbol)}`)}
          sx={{
            flexShrink: 0, px: 1.5, py: 0.75, borderRadius: 10,
            bgcolor: chipBg, cursor: 'pointer', minHeight: 44,
            display: 'flex', alignItems: 'center',
            '&:hover': { bgcolor: `${primaryColor}22` },
          }}
        >
          <Typography sx={{ fontSize: 11, fontWeight: 700, color: 'text.primary', whiteSpace: 'nowrap' }}>
            {item.symbol}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

// ── Mobile bottom navigation ────────────────────────────────────────────────
// How many `mobile: true` NAV_ITEMS fit in the primary bar on small phones
// (≤375px — iPhone SE and older 320px devices); the rest go to the More drawer.
const SMALL_PHONE_PRIMARY_COUNT = 2;

function MobileNav() {
  const pathname                 = usePathname();
  const { isDark, primaryColor } = useAppShell();
  const { user, signOut }        = useAuth();
  const [moreOpen,  setMoreOpen] = useState(false);
  const [authOpen,  setAuthOpen] = useState(false);
  const isSmallPhone             = useMediaQuery('(max-width:375px)');
  const borderCol = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';

  // NAV_ITEMS.mobile (lib/navItems.ts) is the single source of mobile-nav
  // classification — no separate href lists to keep in sync.
  const mobileItems  = NAV_ITEMS.filter(i => i.mobile);
  const primaryNav   = isSmallPhone ? mobileItems.slice(0, SMALL_PHONE_PRIMARY_COUNT) : mobileItems;
  const secondaryNav = NAV_ITEMS.filter(i => !primaryNav.includes(i));
  const moreActive   = secondaryNav.some(i => isActive(pathname, i.href));

  return (
    <>
      <Box
        component="nav"
        sx={{
          display: { xs: 'flex', md: 'none' },
          position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 1200,
          borderTop: `1px solid ${borderCol}`, bgcolor: 'background.paper',
          justifyContent: 'space-around', alignItems: 'stretch', height: 60,
        }}
      >
        {primaryNav.map(({ label, href, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Box
              key={href}
              component={Link}
              href={href}
              sx={{
                flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', gap: 0.25, textDecoration: 'none',
                color: active ? primaryColor : 'text.secondary',
                minHeight: 44,
              }}
            >
              <Icon size={20} color={active ? primaryColor : 'currentColor'} />
              <Typography sx={{ fontSize: 10, fontWeight: active ? 700 : 500 }}>{label}</Typography>
            </Box>
          );
        })}

        {/* Search — opens the command palette as a top sheet (Ctrl+K has no mobile equivalent) */}
        <Box
          onClick={openCommandPalette}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCommandPalette(); } }}
          role="button"
          tabIndex={0}
          aria-label="Search"
          data-testid="palette-search-button"
          sx={{
            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: 0.25, cursor: 'pointer',
            color: 'text.secondary', minHeight: 44,
          }}
        >
          <Search size={20} />
          <Typography sx={{ fontSize: 10, fontWeight: 500 }}>Search</Typography>
        </Box>

        {/* More — opens secondary nav + auth drawer */}
        <Box
          onClick={() => setMoreOpen(true)}
          sx={{
            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: 0.25, cursor: 'pointer',
            color: moreActive ? primaryColor : 'text.secondary',
            minHeight: 44,
          }}
        >
          <MoreHorizontal size={20} color={moreActive ? primaryColor : 'currentColor'} />
          <Typography sx={{ fontSize: 10, fontWeight: moreActive ? 700 : 500 }}>More</Typography>
        </Box>
      </Box>

      {/* More drawer — secondary nav + auth */}
      <Drawer
        anchor="bottom"
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        sx={{ display: { xs: 'block', md: 'none' }, '& .MuiDrawer-paper': { borderRadius: '16px 16px 0 0', pb: 2 } }}
      >
        <Box sx={{ pt: 1, pb: 0.5, display: 'flex', justifyContent: 'center' }}>
          <Box sx={{ width: 36, height: 4, borderRadius: 2, bgcolor: 'divider' }} />
        </Box>

        {/* Auth section — centered profile card */}
        <Box sx={{ px: 2, py: 2.5, borderBottom: `1px solid ${borderCol}`, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1.25 }}>
          {user ? (
            <>
              {/* Avatar: initials in a circle */}
              <Box sx={{
                width: 56, height: 56, borderRadius: '50%',
                bgcolor: `${primaryColor}1e`,
                border: `2px solid ${primaryColor}55`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <Typography sx={{ fontSize: 22, fontWeight: 800, color: primaryColor, lineHeight: 1 }}>
                  {(user.email?.[0] ?? 'U').toUpperCase()}
                </Typography>
              </Box>
              {/* Name + email */}
              <Box sx={{ textAlign: 'center' }}>
                <Typography sx={{ fontSize: 14, fontWeight: 700, lineHeight: 1.3 }}>
                  {user.email?.split('@')[0] ?? 'Account'}
                </Typography>
                <Typography sx={{ fontSize: 11, opacity: 0.5, lineHeight: 1.4 }}>
                  {user.email}
                </Typography>
              </Box>
              <Button
                size="small"
                variant="outlined"
                color="inherit"
                onClick={() => { signOut().catch(console.error); setMoreOpen(false); }}
                startIcon={<LogOut size={14} />}
                sx={{ fontSize: 11, borderRadius: 2, mt: 0.5 }}
              >
                Sign Out
              </Button>
            </>
          ) : (
            <>
              {/* Guest avatar placeholder */}
              <Box sx={{
                width: 56, height: 56, borderRadius: '50%',
                bgcolor: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <LogIn size={24} color={isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.3)'} />
              </Box>
              <Button
                variant="outlined"
                onClick={() => { setMoreOpen(false); setAuthOpen(true); }}
                startIcon={<LogIn size={16} />}
                sx={{ borderRadius: 2 }}
              >
                Sign In
              </Button>
            </>
          )}
        </Box>

        <List disablePadding>
          {secondaryNav.map(({ label, href, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <ListItemButton
                key={href}
                component={Link}
                href={href}
                onClick={() => setMoreOpen(false)}
                sx={{ py: 1.5, color: active ? primaryColor : 'text.primary' }}
              >
                <ListItemIcon sx={{ minWidth: 40, color: 'inherit' }}>
                  <Icon size={20} />
                </ListItemIcon>
                <ListItemText
                  primary={label}
                  slotProps={{ primary: { sx: { fontWeight: active ? 700 : 500, fontSize: '0.9rem' } } }}
                />
              </ListItemButton>
            );
          })}
        </List>
      </Drawer>

      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
    </>
  );
}

// ── Shell ───────────────────────────────────────────────────────────────────
function Shell({ children }: { children: React.ReactNode }) {
  const { watchlist } = useWatchlistContext();

  return (
    <Box data-testid="app-shell" sx={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <Box
        component="main"
        sx={{
          flexGrow: 1, minWidth: 0,
          overflowY: 'auto',
          px: { xs: 2, sm: 3 },
          pt: { xs: 2, sm: 3 },
          // Bottom clearance: fixed nav (60px) + optional watchlist bar (48px) + iOS safe-area inset
          pb: {
            xs: watchlist.length > 0
              ? 'calc(120px + env(safe-area-inset-bottom, 0px))'
              : 'calc(80px + env(safe-area-inset-bottom, 0px))',
            md: 3,
          },
          // 4K: centre main content, prevent full-width sprawl
          maxWidth: { '2xl': 1600 },
          mx: 'auto',
        }}
      >
        {children}
      </Box>
      <MobileWatchlistBar />
      <MobileNav />
      <CommandPalette />
    </Box>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShellProvider>
      <Shell>{children}</Shell>
    </AppShellProvider>
  );
}
