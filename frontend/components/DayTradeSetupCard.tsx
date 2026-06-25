'use client';

import { Box, Card, CardContent, Chip, Skeleton, Stack, Typography } from '@mui/material';
import { AlertTriangle, Banknote, CheckCircle2, Clock, Shield, Target, Zap } from 'lucide-react';
import type { DayTradeSetup } from '../types';

interface Props {
  setup:        DayTradeSetup | null;
  loading:      boolean;
  isDark:       boolean;
  primaryColor: string;
}

/** A single intraday level cell (OR high/low, VWAP, last). Module-scoped so it's
 *  a stable component, not re-created on every render. */
function Level({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Box sx={{ textAlign: 'center', flex: 1 }}>
      <Typography sx={{ fontSize: '0.55rem', opacity: 0.5, letterSpacing: '0.05em', fontWeight: 700 }}>
        {label}
      </Typography>
      <Typography sx={{ fontSize: '0.72rem', fontWeight: 800, color: color ?? 'inherit' }}>
        ${value.toFixed(2)}
      </Typography>
    </Box>
  );
}

export default function DayTradeSetupCard({ setup, loading, isDark, primaryColor }: Props) {
  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';
  const amber = isDark ? '#ffb020' : '#b45309';

  if (loading) {
    return <Skeleton variant="rectangular" height={140} sx={{ borderRadius: 2 }} />;
  }
  if (!setup) return null;

  const dirColor = setup.direction === 'Short' ? red
                 : setup.direction === 'Long'  ? green : amber;

  // A "watch" state (not available) shows the reason; "ok" shows the full plan.
  const watch = !setup.available;

  return (
    <Card sx={{ border: `1px solid ${dirColor}33` }}>
      <CardContent sx={{ p: '16px !important' }}>
        {/* Header */}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Zap size={16} color={primaryColor} />
            <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
              Day Trade · ORB
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1}>
            {!watch && setup.direction !== 'Neutral' && (
              <Chip
                label={setup.direction.toUpperCase()}
                size="small"
                sx={{
                  fontSize: '0.65rem', fontWeight: 800, letterSpacing: '0.04em',
                  background: `${dirColor}22`, color: dirColor, border: `1px solid ${dirColor}66`,
                }}
              />
            )}
            {!watch && setup.risk_reward && (
              <Chip
                label={`R:R ${setup.risk_reward}`}
                size="small"
                sx={{
                  fontSize: '0.65rem', fontWeight: 700,
                  background: `${green}18`, color: green, border: `1px solid ${green}44`,
                }}
              />
            )}
          </Stack>
        </Stack>

        {/* Strategy line */}
        <Typography sx={{ fontSize: '0.62rem', opacity: 0.45, mb: 1.25 }}>
          {setup.strategy}
        </Typography>

        {watch ? (
          /* Not actionable — explain why (closed / forming / conflict). */
          <Box sx={{
            display: 'flex', gap: 1, alignItems: 'flex-start',
            p: 1.5, borderRadius: 2, border: `1px solid ${amber}55`, background: `${amber}12`,
          }}>
            <Box sx={{ mt: '1px', flexShrink: 0 }}><AlertTriangle size={15} color={amber} /></Box>
            <Typography sx={{ fontSize: '0.78rem', lineHeight: 1.5, color: amber }}>
              {setup.message}
            </Typography>
          </Box>
        ) : (
          <>
            {/* Entry / Stop / Targets */}
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr 1fr' }, gap: 1.5, mb: 1.5 }}>
              <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${primaryColor}22`, background: `${primaryColor}08` }}>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
                  <Target size={12} color={primaryColor} />
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>ENTRY</Typography>
                </Stack>
                <Typography sx={{ fontSize: '0.8rem', fontWeight: 800, color: primaryColor }}>
                  ${setup.entry!.toFixed(2)}
                </Typography>
                <Typography sx={{ fontSize: '0.55rem', opacity: 0.6 }}>OR breakout</Typography>
              </Box>
              <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${red}22`, background: `${red}08` }}>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
                  <Shield size={12} color={red} />
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>STOP</Typography>
                </Stack>
                <Typography sx={{ fontSize: '0.8rem', fontWeight: 800, color: red }}>
                  ${setup.stop!.toFixed(2)}
                </Typography>
                <Typography sx={{ fontSize: '0.55rem', opacity: 0.6 }}>VWAP / OR edge</Typography>
              </Box>
              <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${green}22`, background: `${green}08` }}>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
                  <Target size={12} color={green} />
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>TARGETS</Typography>
                </Stack>
                {(setup.targets ?? []).map((t, i) => (
                  <Typography key={i} sx={{ fontSize: '0.7rem', fontWeight: i === 0 ? 800 : 600, color: green, opacity: 1 - i * 0.2 }}>
                    T{i + 1} ${t.toFixed(2)}
                  </Typography>
                ))}
              </Box>
            </Box>

            {/* Intraday levels */}
            {setup.levels && (
              <Stack direction="row" sx={{
                px: 1, py: 1, mb: 1.5, borderRadius: 1.5,
                background: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}>
                <Level label="OR HIGH" value={setup.levels.or_high} />
                <Level label="VWAP" value={setup.levels.vwap} color={primaryColor} />
                <Level label="OR LOW" value={setup.levels.or_low} />
                <Level label="LAST" value={setup.levels.last} />
              </Stack>
            )}

            {/* Entry trigger */}
            {setup.entry_trigger && (() => {
              const active = setup.confirmation === 'active';
              const c = active ? green : amber;
              const Icon = active ? CheckCircle2 : Clock;
              return (
                <Box sx={{
                  display: 'flex', gap: 1, alignItems: 'flex-start',
                  p: 1.25, mb: 1.5, borderRadius: 1.5, border: `1px solid ${c}44`, background: `${c}0f`,
                }}>
                  <Box sx={{ mt: '1px', flexShrink: 0 }}><Icon size={14} color={c} /></Box>
                  <Box>
                    <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, letterSpacing: '0.05em', color: c, mb: 0.25 }}>
                      {active ? 'BREAKOUT ACTIVE' : 'TRIGGER · PENDING'}
                    </Typography>
                    <Typography sx={{ fontSize: '0.72rem', opacity: 0.8, lineHeight: 1.45 }}>
                      {setup.entry_trigger}
                    </Typography>
                  </Box>
                </Box>
              );
            })()}

            {/* CFD framing */}
            {setup.cfd_note && (
              <Box sx={{
                display: 'flex', gap: 1, alignItems: 'flex-start',
                p: 1.25, borderRadius: 1.5, border: `1px solid ${primaryColor}33`, background: `${primaryColor}0a`,
              }}>
                <Box sx={{ mt: '1px', flexShrink: 0 }}><Banknote size={14} color={primaryColor} /></Box>
                <Box>
                  <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, letterSpacing: '0.05em', color: primaryColor, mb: 0.25 }}>
                    CFD {setup.cfd_side ? `· ${setup.cfd_side.toUpperCase()}` : ''}
                    {setup.cfd_margin_pct != null ? ` · ~${setup.cfd_margin_pct}% MARGIN` : ''}
                  </Typography>
                  <Typography sx={{ fontSize: '0.72rem', opacity: 0.75, lineHeight: 1.45 }}>
                    {setup.cfd_note}
                  </Typography>
                </Box>
              </Box>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
