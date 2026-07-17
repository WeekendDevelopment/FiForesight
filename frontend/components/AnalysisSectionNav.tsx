'use client';

import { Box, Chip } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useAppShell } from '../contexts/AppShellContext';

export interface AnalysisSectionDef {
  id:    string;
  label: string;
}

interface Props {
  sections:         ReadonlyArray<AnalysisSectionDef>;
  activeId:         string;
  onJump:           (id: string) => void;
  collapsed:        Record<string, boolean>;
  onToggleCollapse: (id: string) => void;
}

/**
 * Sticky chip navigator for the analysis page's section groups (Feature 34).
 * One chip per section; the active one (tracked by an IntersectionObserver in
 * the page) is highlighted. Clicking a chip jumps to its section — expanding
 * it first if it was collapsed, so a jump never lands on a closed group.
 */
export default function AnalysisSectionNav({ sections, activeId, onJump, collapsed, onToggleCollapse }: Props) {
  const theme = useTheme();
  const { primaryColor } = useAppShell();

  return (
    <Box
      component="nav"
      role="navigation"
      aria-label="Analysis sections"
      data-testid="analysis-section-nav"
      sx={{
        position: 'sticky',
        top: 0,
        // Above the cards scrolling under it, below the mobile fixed bars
        // (watchlist 1199 / bottom nav 1200 / chat FAB 1201).
        zIndex: 1150,
        // Glassy backdrop so cards sliding underneath read as "behind" the nav.
        backdropFilter: 'blur(14px)',
        WebkitBackdropFilter: 'blur(14px)',
        bgcolor: alpha(theme.palette.background.default, 0.75),
        borderBottom: `1px solid ${alpha(theme.palette.divider, 0.6)}`,
        // Bleed over the parent Stack's edges slightly so sticky content
        // doesn't show at the rounded chip corners.
        mx: -0.5,
        px: 0.5,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          flexWrap: 'nowrap',
          gap: 1,
          py: 1,
          // 320px: chips scroll horizontally instead of wrapping/overflowing.
          overflowX: 'auto',
          '&::-webkit-scrollbar': { display: 'none' },
          scrollbarWidth: 'none',
        }}
      >
        {sections.map(({ id, label }) => {
          const active      = id === activeId;
          const isCollapsed = !!collapsed[id];
          return (
            <Chip
              key={id}
              component="button"
              label={label}
              clickable
              onClick={() => {
                if (isCollapsed) onToggleCollapse(id);
                onJump(id);
              }}
              aria-current={active ? 'true' : undefined}
              sx={{
                flexShrink: 0,
                minHeight: 36,   // comfortable touch target
                px: 0.5,
                fontWeight: 700,
                fontSize: 13,
                cursor: 'pointer',
                opacity: isCollapsed && !active ? 0.55 : 1,
                bgcolor: active ? `${primaryColor}22` : 'transparent',
                color: active ? primaryColor : 'text.secondary',
                border: `1px solid ${active ? primaryColor : alpha(theme.palette.divider, 0.8)}`,
                transition: 'background 0.15s ease, color 0.15s ease, border-color 0.15s ease',
                '&:hover': { bgcolor: active ? `${primaryColor}2e` : alpha(theme.palette.text.primary, 0.06) },
              }}
            />
          );
        })}
      </Box>
    </Box>
  );
}
