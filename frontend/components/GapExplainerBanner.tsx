'use client';
import React, { useState } from 'react';
import { Alert, AlertTitle, Box, Collapse, Link, Typography } from '@mui/material';
import type { GapAlert } from '../types';

interface Props {
  alert: GapAlert | null;
  /** Ticker shown in the title row (the alert payload carries no symbol). */
  symbol?: string;
}

/**
 * Full-width banner shown above the price chart when a stock moves >=3% from
 * yesterday's close (Feature 22). Green for an up gap, red for a down gap.
 * Not dismissable — it clears itself on the next ticker search.
 */
export default function GapExplainerBanner({ alert, symbol }: Props) {
  const [showHeadlines, setShowHeadlines] = useState(false);

  if (!alert) return null;

  const isUp = alert.direction === 'up';
  const signed = `${alert.gapPct > 0 ? '+' : ''}${alert.gapPct.toFixed(1)}%`;
  const label = symbol ? `${symbol} moved ${signed} today` : `Moved ${signed} today`;
  const headlines = alert.headlines?.filter(Boolean) ?? [];

  return (
    <Alert severity={isUp ? 'success' : 'error'} sx={{ mb: 2 }}>
      <AlertTitle sx={{ fontWeight: 700 }}>{label}</AlertTitle>

      {alert.explanation && (
        <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
          {alert.explanation}
        </Typography>
      )}

      {headlines.length > 0 && (
        <Box sx={{ mt: 0.5 }}>
          <Link
            component="button"
            type="button"
            underline="hover"
            variant="caption"
            onClick={() => setShowHeadlines(v => !v)}
            sx={{ fontWeight: 600 }}
          >
            {showHeadlines ? 'Hide headlines' : 'Top headlines'}
          </Link>
          <Collapse in={showHeadlines}>
            <Box component="ul" sx={{ pl: 2.5, mt: 0.5, mb: 0 }}>
              {headlines.map((h, i) => (
                <Typography component="li" variant="caption" key={i} sx={{ display: 'list-item' }}>
                  {h}
                </Typography>
              ))}
            </Box>
          </Collapse>
        </Box>
      )}
    </Alert>
  );
}
