'use client';

import React, { useState } from 'react';
import {
  Box, Card, CardContent, Typography, TextField, Button,
  CircularProgress, Chip, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow,
} from '@mui/material';
import { BarChart2 } from 'lucide-react';

interface PeerData {
  symbol:         string;
  name:           string;
  sector:         string;
  price:          string;
  market_cap:     string;
  pe_ratio:       string;
  forward_pe:     string;
  peg_ratio:      string;
  ev_to_ebitda:   string;
  beta:           string;
  revenue_growth: string;
  range_52w:      string;
}

interface Props {
  baseSymbol:   string;
  isDark:       boolean;
  primaryColor: string;
}

const METRICS: { key: keyof PeerData; label: string }[] = [
  { key: 'price',          label: 'Price'       },
  { key: 'market_cap',     label: 'Mkt Cap'     },
  { key: 'pe_ratio',       label: 'P/E'         },
  { key: 'forward_pe',     label: 'Fwd P/E'     },
  { key: 'peg_ratio',      label: 'PEG'         },
  { key: 'ev_to_ebitda',   label: 'EV/EBITDA'   },
  { key: 'beta',           label: 'Beta'        },
  { key: 'revenue_growth', label: 'Rev Growth'  },
  { key: 'range_52w',      label: '52W Range'   },
];

function cellColor(key: keyof PeerData, val: string, isDark: boolean): string | undefined {
  const good = isDark ? '#00ffa3' : '#16a34a';
  const bad  = isDark ? '#ff0055' : '#dc2626';
  if (val === 'N/A') return undefined;
  if (key === 'peg_ratio') {
    const n = parseFloat(val);
    return isNaN(n) ? undefined : n < 1 ? good : n > 2 ? bad : undefined;
  }
  if (key === 'beta') {
    const n = parseFloat(val);
    return isNaN(n) ? undefined : n > 1.5 ? bad : n < 0.8 ? good : undefined;
  }
  if (key === 'revenue_growth') {
    return val.startsWith('-') ? bad : good;
  }
  return undefined;
}

export default function PeerComparisonPanel({ baseSymbol, isDark, primaryColor }: Props) {
  const [input,   setInput]   = useState('');
  const [peers,   setPeers]   = useState<PeerData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const handleCompare = async () => {
    const extra = input.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
    const all   = Array.from(new Set([baseSymbol, ...extra])).slice(0, 6).join(',');
    setLoading(true);
    setError(null);
    try {
      const res  = await fetch(`/api/compare?symbols=${encodeURIComponent(all)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Compare failed');
      setPeers(data.peers ?? []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          <BarChart2 size={16} style={{ color: primaryColor }} />
          <Typography variant="overline" sx={{ opacity: 0.5 }}>Peer Comparison</Typography>
        </Stack>

        <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
          <Chip label={baseSymbol} size="small" sx={{ fontWeight: 800, background: `${primaryColor}22`, color: primaryColor }} />
          <TextField
            size="small"
            placeholder="Add tickers: AAPL, MSFT…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCompare()}
            sx={{ flex: 1, '& .MuiInputBase-root': { fontSize: '0.75rem' } }}
          />
          <Button
            size="small" variant="outlined"
            onClick={handleCompare}
            disabled={loading}
            sx={{ minWidth: 80, fontSize: '0.65rem', fontWeight: 800 }}
          >
            {loading ? <CircularProgress size={14} /> : 'COMPARE'}
          </Button>
        </Stack>

        {error && (
          <Typography variant="caption" color="error" sx={{ display: 'block', mb: 1 }}>
            {error}
          </Typography>
        )}

        {peers.length > 0 && (
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small" sx={{ minWidth: 400 }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontSize: '0.6rem', opacity: 0.4, fontWeight: 800, letterSpacing: 1, py: 0.75 }}>
                    METRIC
                  </TableCell>
                  {peers.map(p => (
                    <TableCell key={p.symbol} align="right"
                      sx={{ fontSize: '0.65rem', fontWeight: 900, color: p.symbol === baseSymbol ? primaryColor : 'inherit', py: 0.75 }}>
                      {p.symbol}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {METRICS.map(({ key, label }) => (
                  <TableRow key={key} sx={{ '&:last-child td': { border: 0 } }}>
                    <TableCell sx={{ fontSize: '0.6rem', opacity: 0.4, py: 0.5, whiteSpace: 'nowrap' }}>
                      {label}
                    </TableCell>
                    {peers.map(p => (
                      <TableCell key={p.symbol} align="right"
                        sx={{
                          fontSize: '0.7rem', fontWeight: 700, py: 0.5,
                          color: cellColor(key, p[key], isDark) ?? 'inherit',
                        }}>
                        {key === 'price' ? `$${p[key]}` : p[key]}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
                {/* Sector row */}
                <TableRow>
                  <TableCell sx={{ fontSize: '0.6rem', opacity: 0.4, py: 0.5 }}>Sector</TableCell>
                  {peers.map(p => (
                    <TableCell key={p.symbol} align="right"
                      sx={{ fontSize: '0.6rem', opacity: 0.55, py: 0.5, maxWidth: 80 }}>
                      <Box sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {p.sector}
                      </Box>
                    </TableCell>
                  ))}
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
}
