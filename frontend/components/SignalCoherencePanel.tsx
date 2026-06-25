'use client';

import { Box, Card, CardContent, Stack, Typography } from '@mui/material';
import { Scale, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { PredictionData } from '../types';

interface Props {
  prediction:   PredictionData | null;
  isDark:       boolean;
  primaryColor: string;
}

type Dir = 'bull' | 'bear' | 'neutral';

interface Signal {
  label:   string;
  dir:     Dir;
  read:    string;   // short human value, e.g. "Bullish", "+2.5%", "Down"
  horizon: string;   // what time frame this signal speaks to
}

// Mirror of the jury rating→score map (AnalystJuryPanel) so the jury contributes
// one net direction here too.
const RATING_SCORE: Record<string, number> = {
  'Strong Buy': 2, 'Low Risk': 2, 'Buy': 1, 'Accumulate': 1,
  'Hold': 0, 'Medium Risk': 0,
  'Distribute': -1, 'Sell': -1, 'High Risk': -1, 'Strong Sell': -2,
};

/** Collect the directional/timing signals the app already produces. Value signals
 *  (DCF, analyst price targets) are deliberately excluded — they answer a
 *  different, longer-horizon question and are noted in the explainer instead. */
function buildSignals(p: PredictionData): Signal[] {
  const out: Signal[] = [];
  const price = parseFloat(p.currentPrice);

  // 1. Short-term trend (price structure + momentum)
  const t = p.prediction.trend;
  out.push({
    label: 'Trend', read: t, horizon: 'short-term',
    dir: t === 'Bullish' ? 'bull' : t === 'Bearish' ? 'bear' : 'neutral',
  });

  // 2. 5-day ensemble forecast (central path endpoint vs spot)
  const fc = p.forecastDays?.[p.forecastDays.length - 1]?.predicted;
  if (fc != null && price > 0) {
    const chg = (fc - price) / price;
    out.push({
      label: '5-Day Model',
      read: `${chg >= 0 ? '+' : ''}${(chg * 100).toFixed(1)}%`,
      horizon: '5-day',
      dir: chg > 0.01 ? 'bull' : chg < -0.01 ? 'bear' : 'neutral',
    });
  }

  // 3. Market regime (HMM state)
  const rg = p.regime?.regime;
  if (rg && rg !== 'unknown') {
    out.push({
      label: 'Regime',
      read: rg.replace(/_/g, ' '),
      horizon: 'multi-week',
      dir: rg === 'trending_up' ? 'bull' : rg === 'trending_down' ? 'bear' : 'neutral',
    });
  }

  // 4. Next-day RF classifier
  const df = p.directionForecast;
  if (df) {
    out.push({
      label: 'Next-Day',
      read: df.direction === 'up' ? 'Up' : 'Down',
      horizon: 'next-day',
      dir: df.direction === 'up' ? 'bull' : 'bear',
    });
  }

  // 5. Analyst jury (only when verdicts are present — it runs on demand)
  const jury = p.juryAnalysts ?? [];
  if (jury.length > 0) {
    const mean = jury.reduce((s, a) => s + (RATING_SCORE[a.rating] ?? 0), 0) / jury.length;
    out.push({
      label: 'Jury',
      read: mean > 0.3 ? 'Bullish' : mean < -0.3 ? 'Bearish' : 'Hold',
      horizon: 'discretionary',
      dir: mean > 0.3 ? 'bull' : mean < -0.3 ? 'bear' : 'neutral',
    });
  }

  // 6. News sentiment (VADER)
  const sl = p.sentiment?.label;
  if (sl) {
    out.push({
      label: 'Sentiment',
      read: sl,
      horizon: 'news now',
      dir: sl === 'Bullish' ? 'bull' : sl === 'Bearish' ? 'bear' : 'neutral',
    });
  }

  return out;
}

export default function SignalCoherencePanel({ prediction, isDark, primaryColor }: Props) {
  if (!prediction) return null;

  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';
  const amber = isDark ? '#ffb020' : '#b45309';
  const grey  = isDark ? '#64748b' : '#94a3b8';

  const signals = buildSignals(prediction);
  const bull = signals.filter(s => s.dir === 'bull').length;
  const bear = signals.filter(s => s.dir === 'bear').length;
  const neut = signals.filter(s => s.dir === 'neutral').length;
  const decisive = bull + bear;
  const conflict = bull > 0 && bear > 0;
  const coherence = decisive > 0 ? Math.max(bull, bear) / decisive : 0;
  const majorityBull = bull >= bear;

  // Headline verdict — honest about disagreement, which is the whole point.
  let verdict: string;
  let vColor: string;
  let VIcon: typeof TrendingUp;
  if (decisive === 0) {
    verdict = 'Neutral · Range-bound';
    vColor = grey; VIcon = Minus;
  } else if (!conflict) {
    verdict = majorityBull ? 'Aligned · Bullish' : 'Aligned · Bearish';
    vColor = majorityBull ? green : red;
    VIcon  = majorityBull ? TrendingUp : TrendingDown;
  } else if (coherence >= 0.67) {
    verdict = majorityBull ? 'Leaning Bullish · some disagreement'
                           : 'Leaning Bearish · some disagreement';
    vColor = amber;
    VIcon  = majorityBull ? TrendingUp : TrendingDown;
  } else {
    verdict = 'Mixed · Low Conviction';
    vColor = amber; VIcon = Minus;
  }

  const dirColor = (d: Dir) => d === 'bull' ? green : d === 'bear' ? red : grey;
  const DirIcon  = (d: Dir) => d === 'bull' ? TrendingUp : d === 'bear' ? TrendingDown : Minus;

  const explainer = conflict
    ? 'These signals measure different horizons, so they can — and here do — point different ways. Short-term momentum and the next-day model often diverge from the 5-day forecast, the market regime, and long-term value (DCF, analyst targets). Weight them by your own time frame rather than trading every box at once.'
    : 'Most directional signals agree here. They still cover different horizons (next-day → multi-week) and exclude long-term value (DCF, analyst targets) — treat this as a timing read, not a full thesis.';

  return (
    <Card sx={{ border: `1px solid ${vColor}44` }}>
      <CardContent sx={{ p: '16px !important' }}>
        {/* Header */}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Scale size={16} color={primaryColor} />
            <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
              Signal Coherence
            </Typography>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={0.75}
                 sx={{ px: 1, py: 0.5, borderRadius: 1.5, background: `${vColor}18`, border: `1px solid ${vColor}55` }}>
            <VIcon size={14} color={vColor} />
            <Typography sx={{ fontSize: '0.72rem', fontWeight: 800, color: vColor, letterSpacing: '0.02em' }}>
              {verdict}
            </Typography>
          </Stack>
        </Stack>

        {/* Conviction meter — bull / neutral / bear proportions */}
        <Box sx={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', mb: 1.5 }}>
          {bull > 0 && <Box sx={{ flex: bull, background: green }} />}
          {neut > 0 && <Box sx={{ flex: neut, background: grey, opacity: 0.4 }} />}
          {bear > 0 && <Box sx={{ flex: bear, background: red }} />}
        </Box>
        <Stack direction="row" justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Typography sx={{ fontSize: '0.62rem', color: green, fontWeight: 700 }}>
            {bull} bullish
          </Typography>
          <Typography sx={{ fontSize: '0.62rem', color: grey, fontWeight: 700 }}>
            {neut} neutral · {signals.length} signals
          </Typography>
          <Typography sx={{ fontSize: '0.62rem', color: red, fontWeight: 700 }}>
            {bear} bearish
          </Typography>
        </Stack>

        {/* Per-signal chips */}
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(3, 1fr)' },
          gap: 1, mb: 1.5,
        }}>
          {signals.map((s) => {
            const c = dirColor(s.dir);
            const Icon = DirIcon(s.dir);
            return (
              <Box key={s.label} sx={{
                p: 1, borderRadius: 1.5, border: `1px solid ${c}33`, background: `${c}0d`,
              }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between">
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.55, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                    {s.label}
                  </Typography>
                  <Icon size={12} color={c} />
                </Stack>
                <Typography sx={{ fontSize: '0.78rem', fontWeight: 800, color: c, lineHeight: 1.2, textTransform: 'capitalize' }}>
                  {s.read}
                </Typography>
                <Typography sx={{ fontSize: '0.55rem', opacity: 0.4 }}>
                  {s.horizon}
                </Typography>
              </Box>
            );
          })}
        </Box>

        {/* Explainer */}
        <Typography sx={{ fontSize: '0.72rem', opacity: 0.65, lineHeight: 1.5 }}>
          {explainer}
        </Typography>
      </CardContent>
    </Card>
  );
}
