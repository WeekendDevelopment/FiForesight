'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import {
  Box, Stack, Typography, IconButton, Tooltip, useMediaQuery,
} from '@mui/material';
import {
  BrainCircuit, Home, Search, BarChart2, Calendar, Rocket, LineChart,
  Activity, ChevronLeft, ChevronRight, Sun, Moon, LogIn, LogOut,
} from 'lucide-react';
import { AppShellProvider, useAppShell } from '../../contexts/AppShellContext';
import { useAuth } from '../../contexts/AuthContext';
import AuthModal from '../../components/AuthModal';

// ── Navigation model ────────────────────────────────────────────────────────
interface NavItem {
  label: string;
  href:  string;
  icon:  React.ComponentType<{ size?: number | string; color?: string }>;
  /** Shown in the mobile bottom nav (Portfolio is desktop-only / secondary). */
  mobile: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Home',        href: '/',           icon: Home,      mobile: true  },
  { label: 'Analysis',    href: '/analysis',   icon: Search,    mobile: true  },
  { label: 'Options',     href: '/options',    icon: BarChart2, mobile: true  },
  { label: 'Earnings',    href: '/earnings',   icon: Calendar,  mobile: true  },
  { label: 'IPO Tracker', href: '/ipo',        icon: Rocket,    mobile: true  },
  { label: 'Insights',    href: '/insights',   icon: Activity,  mobile: false },
  { label: 'Portfolio',   href: '/simulation', icon: LineChart, mobile: false },
];

const EXPANDED_WIDTH  = 220;
const COLLAPSED_WIDTH = 64;
const COLLAPSE_KEY    = 'sidebar_collapsed';

// Active when the path matches exactly, or (for non-root items) is nested under it.
function isActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}

// ── Desktop sidebar ─────────────────────────────────────────────────────────
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

// ── Mobile bottom navigation ────────────────────────────────────────────────
function MobileNav() {
  const pathname = usePathname();
  const { isDark, primaryColor } = useAppShell();
  const items = NAV_ITEMS.filter(i => i.mobile);
  const borderCol = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';

  return (
    <Box
      component="nav"
      sx={{
        display: { xs: 'flex', md: 'none' },
        position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 1200,
        borderTop: `1px solid ${borderCol}`, bgcolor: 'background.paper',
        justifyContent: 'space-around', alignItems: 'stretch', height: 60,
      }}
    >
      {items.map(({ label, href, icon: Icon }) => {
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
            }}
          >
            <Icon size={20} color={active ? primaryColor : 'currentColor'} />
            <Typography sx={{ fontSize: 10, fontWeight: active ? 700 : 500 }}>{label}</Typography>
          </Box>
        );
      })}
    </Box>
  );
}

// ── Shell ───────────────────────────────────────────────────────────────────
function Shell({ children }: { children: React.ReactNode }) {
  const isMobile = useMediaQuery('(max-width:899.95px)');
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <Box
        component="main"
        sx={{
          flexGrow: 1, minWidth: 0,
          overflowY: 'auto',
          p: 3,
          pb: isMobile ? 9 : 3, // leave room for the mobile bottom nav
        }}
      >
        {children}
      </Box>
      <MobileNav />
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
