'use client';

import { useState } from 'react';
import {
  Box, Card, CardContent, Chip, MenuItem, Select, Stack,
  Table, TableBody, TableCell, TableHead, TableRow, Tabs, Tab, Typography,
} from '@mui/material';
import { Activity } from 'lucide-react';
import type { OptionsChainResult, OptionContract } from '../types';

interface Props {
  data:            OptionsChainResult;
  isDark:          boolean;
  primaryColor:    string;
  onExpiryChange?: (expiry: string) => void;
}

const cell = { fontSize: '0.68rem', py: 0.5, px: 1 };

function ContractRow({ c, isDark }: { c: OptionContract; isDark: boolean }) {
  const itm   = c.in_the_money;
  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';
  const itmBg = c.type === 'call'
    ? (itm ? `${green}10` : 'transparent')
    : (itm ? `${red}10`   : 'transparent');

  return (
    <TableRow sx={{ background: itmBg, '&:hover': { opacity: 0.85 } }}>
      <TableCell sx={{ ...cell, fontWeight: itm ? 800 : 400, color: c.type === 'call' ? green : red }}>
        {c.strike.toFixed(2)}
      </TableCell>
      <TableCell sx={cell}>{c.last.toFixed(2)}</TableCell>
      <TableCell sx={cell}>{c.bid.toFixed(2)}</TableCell>
      <TableCell sx={cell}>{c.ask.toFixed(2)}</TableCell>
      <TableCell sx={{ ...cell, color: c.change_pct >= 0 ? green : red }}>
        {c.change_pct >= 0 ? '+' : ''}{c.change_pct.toFixed(2)}%
      </TableCell>
      <TableCell sx={cell}>{c.volume.toLocaleString()}</TableCell>
      <TableCell sx={cell}>{c.open_interest.toLocaleString()}</TableCell>
      <TableCell sx={{ ...cell, fontFamily: 'monospace' }}>{c.implied_vol.toFixed(1)}%</TableCell>
    </TableRow>
  );
}

export default function OptionsChainPanel({ data, isDark, primaryColor, onExpiryChange }: Props) {
  const [tab, setTab] = useState<0 | 1>(0); // 0=calls 1=puts

  const contracts = tab === 0 ? data.calls : data.puts;

  return (
    <Card>
      <CardContent sx={{ p: '16px !important' }}>
        {/* Header */}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Activity size={16} color={primaryColor} />
            <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
              Options Chain
            </Typography>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Chip
              label={`$${data.current_price.toFixed(2)}`}
              size="small"
              sx={{
                fontSize: '0.62rem', fontWeight: 700,
                background: `${primaryColor}18`, color: primaryColor,
                border: `1px solid ${primaryColor}44`,
              }}
            />
            <Select
              value={data.expiry}
              size="small"
              onChange={e => onExpiryChange?.(e.target.value)}
              sx={{ fontSize: '0.65rem', height: 26, '.MuiSelect-select': { py: 0.25, px: 1 } }}
            >
              {data.expirations.map(exp => (
                <MenuItem key={exp} value={exp} sx={{ fontSize: '0.65rem' }}>{exp}</MenuItem>
              ))}
            </Select>
          </Stack>
        </Stack>

        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 1, minHeight: 32 }}>
          <Tab label={`Calls (${data.calls.length})`} sx={{ fontSize: '0.7rem', minHeight: 32, py: 0 }} />
          <Tab label={`Puts (${data.puts.length})`}   sx={{ fontSize: '0.7rem', minHeight: 32, py: 0 }} />
        </Tabs>

        <Box sx={{ overflowX: 'auto', maxHeight: 320, overflowY: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {['Strike', 'Last', 'Bid', 'Ask', 'Chg%', 'Vol', 'OI', 'IV%'].map(h => (
                  <TableCell
                    key={h}
                    sx={{
                      ...cell, fontWeight: 700, opacity: 0.5,
                      fontSize: '0.6rem', letterSpacing: '0.05em', background: 'inherit',
                    }}
                  >
                    {h}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {contracts.map((c, i) => (
                <ContractRow key={i} c={c} isDark={isDark} />
              ))}
              {contracts.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} sx={{ textAlign: 'center', opacity: 0.4, fontSize: '0.7rem' }}>
                    No contracts
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Box>
      </CardContent>
    </Card>
  );
}
