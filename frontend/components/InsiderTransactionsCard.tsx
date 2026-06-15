'use client';

import {
  Accordion, AccordionDetails, AccordionSummary,
  Box, Card, Chip, Link, Skeleton, Stack, Typography,
} from '@mui/material';
import { ChevronDown, Users } from 'lucide-react';
import type { InsiderTransaction } from '../types';

interface Props {
  transactions: InsiderTransaction[];
  loading?:     boolean;
  isDark:       boolean;
  primaryColor: string;
}

/** Colour for a transaction-type chip: green buy, red sell, grey other. */
function typeChipSx(type: string, isDark: boolean) {
  const t = type.toLowerCase();
  if (t.includes('purchase') || t.includes('buy')) {
    return {
      color: isDark ? '#00ffa3' : '#16a34a',
      bgcolor: isDark ? 'rgba(0,255,163,0.12)' : 'rgba(22,163,74,0.12)',
    };
  }
  if (t.includes('sale') || t.includes('sell')) {
    return {
      color: isDark ? '#ff0055' : '#dc2626',
      bgcolor: isDark ? 'rgba(255,0,85,0.12)' : 'rgba(220,38,38,0.12)',
    };
  }
  return {
    color: 'text.secondary',
    bgcolor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
  };
}

export default function InsiderTransactionsCard({
  transactions, loading = false, isDark, primaryColor,
}: Props) {
  const hasPurchases = transactions.some(t => {
    const ty = t.type.toLowerCase();
    return ty.includes('purchase') || ty.includes('buy');
  });
  const borderCol = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';

  return (
    <Card>
      <Accordion
        disableGutters
        defaultExpanded={hasPurchases}
        sx={{ background: 'transparent', boxShadow: 'none', '&:before': { display: 'none' } }}
      >
        <AccordionSummary expandIcon={<ChevronDown size={16} />} sx={{ px: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Users size={14} color={primaryColor} />
            <Typography variant="overline" sx={{ opacity: 0.6, lineHeight: 1 }}>
              Insider Transactions
            </Typography>
            {transactions.length > 0 && (
              <Chip
                label={transactions.length}
                size="small"
                sx={{ height: 16, fontSize: '0.6rem', fontWeight: 700, '& .MuiChip-label': { px: 0.75 } }}
              />
            )}
          </Stack>
        </AccordionSummary>
        <AccordionDetails sx={{ px: 2, pt: 0 }}>
          {loading ? (
            <Stack spacing={1}>
              {[0, 1, 2].map(i => <Skeleton key={i} variant="rounded" height={28} />)}
            </Stack>
          ) : transactions.length === 0 ? (
            <Typography variant="caption" sx={{ opacity: 0.4 }}>
              No recent insider transactions found.
            </Typography>
          ) : (
            <Box sx={{ overflowX: 'auto', mx: -0.5, px: 0.5 }}>
            <Box component="table" sx={{ width: '100%', minWidth: 360, borderCollapse: 'collapse', fontSize: '0.72rem' }}>
              <Box component="thead">
                <Box component="tr" sx={{ opacity: 0.45, textAlign: 'left' }}>
                  {['Date', 'Filer', 'Type', 'Shares', 'Price', ''].map((h, i) => (
                    <Box
                      component="th"
                      key={h || `sec-${i}`}
                      sx={{ py: 0.5, fontWeight: 700, letterSpacing: 0.5, whiteSpace: 'nowrap' }}
                    >
                      {h}
                    </Box>
                  ))}
                </Box>
              </Box>
              <Box component="tbody">
                {transactions.map((t, i) => (
                  <Box
                    component="tr"
                    key={`${t.sec_link}-${t.date}-${i}`}
                    sx={{ borderTop: `1px solid ${borderCol}` }}
                  >
                    <Box component="td" sx={{ py: 0.6, whiteSpace: 'nowrap' }}>{t.date || '—'}</Box>
                    <Box
                      component="td"
                      sx={{
                        py: 0.6, fontWeight: 600, maxWidth: 120,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}
                      title={t.filer}
                    >
                      {t.filer}
                    </Box>
                    <Box component="td" sx={{ py: 0.6 }}>
                      <Chip
                        label={t.type}
                        size="small"
                        sx={{
                          height: 18, fontSize: '0.62rem', fontWeight: 700,
                          ...typeChipSx(t.type, isDark),
                          '& .MuiChip-label': { px: 0.75 },
                        }}
                      />
                    </Box>
                    <Box component="td" sx={{ py: 0.6 }}>
                      {t.shares != null ? t.shares.toLocaleString() : '—'}
                    </Box>
                    <Box component="td" sx={{ py: 0.6 }}>
                      {t.price != null ? `$${t.price.toFixed(2)}` : '—'}
                    </Box>
                    <Box component="td" sx={{ py: 0.6, whiteSpace: 'nowrap' }}>
                      {t.sec_link && (
                        <Link
                          href={t.sec_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          underline="hover"
                          sx={{ fontSize: '0.66rem', color: primaryColor }}
                        >
                          View on SEC
                        </Link>
                      )}
                    </Box>
                  </Box>
                ))}
              </Box>
            </Box>
            </Box>
          )}
        </AccordionDetails>
      </Accordion>
    </Card>
  );
}
