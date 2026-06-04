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

// Ordered most-bullish → most-bearish across all 3 persona rating vocabularies
const RATING_ORDER = [
  'Strong Buy', 'Buy', 'Accumulate', 'Low Risk',
  'Hold', 'Medium Risk',
  'Distribute', 'Sell', 'High Risk', 'Strong Sell',
];

// Friendly labels for the Groq function-calling tools each analyst can invoke.
const TOOL_LABELS: Record<string, string> = {
  get_vix:            'VIX',
  get_put_call_ratio: 'put/call ratio',
  get_insider_flow:   'insider flow',
  get_macro_snapshot: 'macro snapshot',
};

const formatToolsUsed = (tools?: string[]): string => {
  if (!tools || tools.length === 0) return '';
  const labels = Array.from(new Set(tools.map((t) => TOOL_LABELS[t] ?? t)));
  return labels.join(', ');
};

export default function AnalystJuryPanel({ analysts }: { analysts: AnalystJuror[] }) {
  const ratingColor = (r: string) => RATING_COLORS[r] ?? { bg: '#64748b22', text: '#94a3b8' };

  const ratingCounts = analysts.reduce((acc, a) => {
    acc[a.rating] = (acc[a.rating] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
  const consensus = RATING_ORDER.find(r => ratingCounts[r]) ?? analysts[0]?.rating ?? 'Hold';
  const avgConf   = Math.round(analysts.reduce((s, a) => s + a.confidence, 0) / Math.max(analysts.length, 1));
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

                  {formatToolsUsed(analyst.tools_used) && (
                    <Typography sx={{
                      fontSize: '0.5rem', opacity: 0.4, lineHeight: 1.3,
                      fontFamily: 'monospace', color: analyst.color,
                      letterSpacing: '0.02em',
                    }}>
                      🔧 Used: {formatToolsUsed(analyst.tools_used)}
                    </Typography>
                  )}

                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    </Stack>
  );
}
