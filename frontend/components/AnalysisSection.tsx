'use client';

import React from 'react';
import { Box, Collapse, IconButton, Stack, Typography } from '@mui/material';
import { ChevronDown } from 'lucide-react';

interface Props {
  /** Section key ('overview' | 'forecast' | …) — the DOM id becomes `analysis-section-${id}`. */
  id:        string;
  label:     string;
  /** Best-effort number of cards currently rendered inside the section. */
  count?:    number;
  collapsed: boolean;
  onToggle:  () => void;
  children:  React.ReactNode;
}

/**
 * Collapsible section group for the analysis page (Feature 34).
 *
 * IMPORTANT: the body uses MUI <Collapse> WITHOUT unmountOnExit — several cards
 * (StockReportCard, DividendIncomeCard, OrderBookPanel, …) self-fetch on mount,
 * so collapsing must hide them, never unmount them, or every expand would
 * refetch. scroll-margin-top keeps jump-to targets clear of the sticky nav.
 */
export default function AnalysisSection({ id, label, count, collapsed, onToggle, children }: Props) {
  const domId = `analysis-section-${id}`;
  return (
    <Box id={domId} sx={{ scrollMarginTop: 64 }}>
      {/* Slim header row — whole row toggles; the IconButton is the accessible control. */}
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        onClick={onToggle}
        sx={{
          cursor: 'pointer',
          userSelect: 'none',
          px: 0.5,
          mb: collapsed ? 0 : 1.5,
          '&:hover .MuiTypography-overline': { opacity: 0.9 },
        }}
      >
        <Typography variant="overline" sx={{ opacity: 0.6, fontWeight: 700, letterSpacing: 1.2, lineHeight: 1 }}>
          {label}
        </Typography>
        {count != null && count > 0 && (
          <Typography variant="caption" sx={{ opacity: 0.35, lineHeight: 1 }}>
            {count} {count === 1 ? 'card' : 'cards'}
          </Typography>
        )}
        <Box sx={{ flexGrow: 1, borderBottom: '1px solid', borderColor: 'divider', opacity: 0.5 }} />
        <IconButton
          size="small"
          onClick={(e) => { e.stopPropagation(); onToggle(); }}
          aria-expanded={!collapsed}
          aria-controls={`${domId}-content`}
          aria-label={`${collapsed ? 'Expand' : 'Collapse'} ${label} section`}
          sx={{ p: 0.5 }}
        >
          <ChevronDown
            size={16}
            style={{ transform: collapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 0.2s ease' }}
          />
        </IconButton>
      </Stack>

      {/* Children stay mounted while collapsed (no unmountOnExit) — see note above. */}
      <Collapse in={!collapsed} timeout="auto">
        <Stack spacing={3} id={`${domId}-content`}>
          {children}
        </Stack>
      </Collapse>
    </Box>
  );
}
