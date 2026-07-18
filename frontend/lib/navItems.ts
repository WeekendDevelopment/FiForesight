/**
 * Shared navigation model (Feature 33).
 *
 * Lifted out of frontend/app/(app)/layout.tsx so the sidebar, the mobile
 * bottom nav AND the command palette all render from one list — add/remove
 * routes HERE (and mirror the change in tests/e2e/responsive.spec.ts ROUTES).
 */

import {
  Home, Search, BarChart2, Calendar, Rocket, LineChart, Activity, Wallet,
  Bell, Star, Globe, Grid2X2, SlidersHorizontal, RefreshCw, FlaskConical,
} from 'lucide-react';

export interface NavItem {
  label: string;
  href:  string;
  icon:  React.ComponentType<{ size?: number | string; color?: string }>;
  /** Shown in the mobile bottom nav (Insights/Simulator/My Portfolio are desktop-only / secondary). */
  mobile: boolean;
}

// "Simulator" is the backtest race engine (/simulation). "My Portfolio" is the
// real-holdings P&L tracker (/portfolio) — kept clearly distinct so the two
// never get confused.
export const NAV_ITEMS: NavItem[] = [
  { label: 'Home',         href: '/',           icon: Home,      mobile: true  },
  { label: 'Analysis',     href: '/analysis',   icon: Search,    mobile: true  },
  { label: 'Options',      href: '/options',    icon: BarChart2, mobile: true  },
  { label: 'Earnings',     href: '/earnings',   icon: Calendar,  mobile: true  },
  { label: 'IPO Tracker',  href: '/ipo',        icon: Rocket,    mobile: false },
  { label: 'Macro',        href: '/macro',      icon: Globe,     mobile: false },
  { label: 'Sectors',      href: '/sectors',    icon: Grid2X2,   mobile: false },
  { label: 'Rotation',     href: '/rotation',   icon: RefreshCw, mobile: false },
  { label: 'Screener',     href: '/screener',   icon: SlidersHorizontal, mobile: false },
  { label: 'Backtest',     href: '/backtest',   icon: FlaskConical, mobile: false },
  { label: 'Watchlist',    href: '/watchlist',  icon: Star,      mobile: false },
  { label: 'Insights',     href: '/insights',   icon: Activity,  mobile: false },
  { label: 'Simulator',    href: '/simulation', icon: LineChart, mobile: false },
  { label: 'My Portfolio', href: '/portfolio',  icon: Wallet,    mobile: false },
  { label: 'Alerts',       href: '/alerts',     icon: Bell,      mobile: false },
];
