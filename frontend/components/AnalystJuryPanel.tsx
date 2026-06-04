'use client';

import { Box, Card, CardContent, Grid, Stack, Typography } from '@mui/material';
import { Scale } from 'lucide-react';
import type { AnalystJuror } from '../types';

const RATING_COLORS: Record<string, { bg: string; text: string }> = {
  'Strong Buy':  { bg: '#00ffa322', text: '#00ffa3' },
  'Buy':         { bg: '#00f2ff22', text: '#00f2ff' },
  'Accumulate':  { bg: '#00f2ff18', text: '#00d4e0' },
  'Hold':        { bg: '#f59e0b22', text: '#f59e0b' },
  'Distribute':  { bg: '#f9731618', text: '#fb923c' },
  'Sell':        { bg: '#f9731622', text: '#f97316' },
  'Strong Sell': { bg: '#ff005522', text: '#ff0055' },
  'Low Risk':    { bg: '#00ffa322', text: '#00ffa3' },
  'Medium Risk': { bg: '#f59e0b22', text: '#f59e0b' },
  'High Risk':   { bg: '#ff005522', text: '#ff0055' },
};

export default function AnalystJuryPanel({ analysts }: { analysts: AnalystJuror[] }) {
  const ratingColor = (r: string) => RATING_COLORS[r] ?? { bg: '#64748b22', text: '#94a3b8' };

  // Consensus must reflect what the panel actually said — NOT just the single
  // most-bullish verdict (the old `RATING_ORDER.find` headlined "Strong Buy"
  // even when 2/3 said Hold). Normalize every persona vocabulary onto one
  // bullish(+)→bearish(−) score, take the plurality bucket, break ties by
  // summed confidence, and fall back to the confidence-weighted average.
  const RATING_SCORE: Record<string, number> = {
    'Strong Buy': 2, 'Low Risk': 2,
    'Buy': 1, 'Accumulate': 1,
    'Hold': 0, 'Medium Risk': 0,
    'Distribute': -1, 'Sell': -1, 'High Risk': -1,
    'Strong Sell': -2,
  };
  const scoreToRating = (s: number): string =>
    s >= 1.5 ? 'Strong Buy' : s >= 0.5 ? 'Buy' : s > -0.5 ? 'Hold' : s > -1.5 ? 'Sell' : 'Strong Sell';
  const toBucket = (r: string): string => scoreToRating(RATING_SCORE[r] ?? 0);

  const bucketStats = analysts.reduce((acc, a) => {
    const b = toBucket(a.rating);
    const s = acc[b] ?? { count: 0, conf: 0 };
    s.count += 1; s.conf += a.confidence;
    acc[b] = s;
    return acc;
  }, {} as Record<string, { count: number; conf: number }>);

  const totalConf = analysts.reduce((s, a) => s + a.confidence, 0);
  const weightedScore = totalConf
    ? analysts.reduce((s, a) => s + (RATING_SCORE[a.rating] ?? 0) * a.confidence, 0) / totalConf
    : 0;
  const fallbackBucket = scoreToRating(weightedScore);

  const consensus = Object.entries(bucketStats).sort((a, b) =>
    b[1].count - a[1].count ||                                   // most votes
    b[1].conf  - a[1].conf  ||                                   // then summed confidence
    (a[0] === fallbackBucket ? -1 : b[0] === fallbackBucket ? 1 : 0), // then weighted avg
  )[0]?.[0] ?? fallbackBucket;

  const ratingCounts: Record<string, number> = { [consensus]: bucketStats[consensus]?.count ?? analysts.length };
  const avgConf = Math.round(totalConf / Math.max(analysts.length, 1));
  return (
    <Stack spacing={1.5}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 0.5 }}>
        <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1, fontSize: '1rem' }}>
          <Scale size={18} /> Analyst Jury
        </Typography>
        <Box sx={{
          px: 1.2, py: 0.3, borderRadius: 1,
          background: ratingColor(consensus).bg,
          border: `1px solid ${ratingColor(consensus).text}44`,
          display: 'flex', alignItems: 'center', gap: 0.6,
        }}>
          <Typography sx={{ fontSize: '0.62rem', fontWeight: 900, color: ratingColor(consensus).text, letterSpacing: '0.07em' }}>
            {consensus.toUpperCase()}
          </Typography>
          <Typography sx={{ fontSize: '0.56rem', opacity: 0.55, color: ratingColor(consensus).text }}>
            {avgConf}%
          </Typography>
          <Typography sx={{ fontSize: '0.5rem', opacity: 0.35, color: ratingColor(consensus).text, fontFamily: 'monospace' }}>
            {ratingCounts[consensus] ?? analysts.length}/{analysts.length}
          </Typography>
        </Box>
      </Box>

      <Grid container spacing={1.5}>
        {analysts.map((analyst) => {
          const rc = ratingColor(analyst.rating);
          return (
            <Grid size={{ xs: 12, sm: 4 }} key={analyst.id}>
              <Card sx={{
                height: '100%',
                borderLeft: `3px solid ${analyst.color}66`,
                background: `linear-gradient(135deg, ${analyst.color}06 0%, transparent 55%)`,
              }}>
                <CardContent sx={{ p: '14px !important', display: 'flex', flexDirection: 'column', gap: 1.2 }}>

                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                    <Box sx={{
                      width: 34, height: 34, borderRadius: '8px', flexShrink: 0,
                      background: `${analyst.color}14`,
                      border: `1.5px solid ${analyst.color}40`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Typography sx={{
                        fontSize: '0.52rem', fontWeight: 900, color: analyst.color,
                        letterSpacing: '0.03em', lineHeight: 1, fontFamily: 'monospace',
                      }}>
                        {analyst.avatar}
                      </Typography>
                    </Box>

                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{
                        fontSize: '0.78rem', fontWeight: 900, lineHeight: 1.15,
                        fontFamily: 'monospace', color: analyst.color,
                      }}>
                        {analyst.id}
                      </Typography>
                      <Typography sx={{ fontSize: '0.56rem', opacity: 0.5, lineHeight: 1.2 }}>
                        {analyst.title}
                      </Typography>
                      <Typography sx={{ fontSize: '0.5rem', opacity: 0.28, lineHeight: 1.2, fontFamily: 'monospace' }}>
                        {analyst.model_label}
                      </Typography>
                    </Box>

                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.4, flexShrink: 0 }}>
                      <Box sx={{
                        px: 1, py: 0.25, borderRadius: 0.75,
                        background: rc.bg, border: `1px solid ${rc.text}55`,
                      }}>
                        <Typography sx={{ fontSize: '0.6rem', fontWeight: 900, color: rc.text, letterSpacing: '0.07em', whiteSpace: 'nowrap' }}>
                          {analyst.rating.toUpperCase()}
                        </Typography>
                      </Box>
                      <Typography sx={{ fontSize: '0.54rem', opacity: 0.35, fontFamily: 'monospace' }}>
                        {analyst.confidence}% conf
                      </Typography>
                    </Box>
                  </Box>

                  <Box sx={{ height: '1px', background: `${analyst.color}18` }} />

                  <Typography sx={{ fontSize: '0.8rem', lineHeight: 1.65, opacity: 0.85, flex: 1 }}>
                    {analyst.note}
                  </Typography>

                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    </Stack>
  );
}
