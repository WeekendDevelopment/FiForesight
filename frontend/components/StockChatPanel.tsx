'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Box, Button, Chip, Drawer, IconButton,
  Stack, TextField, Typography,
} from '@mui/material';
import { MessageCircle, Send, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import type { ChatMessage, PredictionData } from '../types';
import { formatPrice } from '../lib/currency';

const BEGINNER_CHIPS = [
  "What does RSI mean for this stock?",
  "Is this a good entry point?",
  "What's the main risk here?",
  "Explain the analyst jury verdicts",
];

const fmt = (n: number | null | undefined, d = 2): string =>
  n == null || !Number.isFinite(n) ? 'N/A' : Number(n).toFixed(d);

function buildContext(prediction: PredictionData) {
  const ind  = prediction.indicators;
  const last = prediction.history?.[prediction.history.length - 1];
  const fib  = ind?.fibonacci ?? null;
  // Prices in the chat context carry the instrument's real quote currency (F35)
  // so the assistant doesn't reason about a GBp (pence) name in dollars.
  const cur = prediction.currency ?? prediction.metrics?.currency ?? 'USD';
  const money = (n: number | null | undefined, d = 2): string =>
    n == null || !Number.isFinite(n) ? 'N/A' : formatPrice(Number(n), cur, { decimals: d });

  // Fibonacci levels the chart actually draws — so the assistant can explain the
  // specific retracements the user is looking at, not just the concept.
  const fibStr = fib
    ? `${fib.direction === 'up' ? 'uptrend' : 'downtrend'} swing ${money(fib.swing_low)}–${money(fib.swing_high)}; ` +
      Object.entries(fib.levels)
        .sort((a, b) => Number(a[0]) - Number(b[0]))
        .map(([r, p]) => `${(Number(r) * 100).toFixed(1)}%=${money(p)}`)
        .join(', ')
    : 'N/A';

  const maStr = last
    ? `SMA20 ${money(prediction.modelStats?.sma_20)}, SMA50 ${money(last.sma50)}, ` +
      `SMA200 ${money(last.sma200)}, EMA20 ${money(last.ema20)}, EMA50 ${money(last.ema50)}`
    : 'N/A';

  const macdStr = last && last.macd != null && last.macd_signal != null
    ? `MACD ${fmt(last.macd, 3)} vs signal ${fmt(last.macd_signal, 3)} ` +
      `(${last.macd > last.macd_signal ? 'bullish' : 'bearish'})`
    : 'N/A';

  const bbStr = last && last.bb_upper != null && last.bb_lower != null
    ? `upper ${money(last.bb_upper)}, mid ${money(last.bb_middle)}, lower ${money(last.bb_lower)}`
    : 'N/A';

  return {
    symbol:          prediction.symbol,
    currentPrice:    `${prediction.currentPrice} ${cur}`,
    rsi:             prediction.rsi,
    trend:           prediction.prediction.trend,
    forecast:        `48h range ${money(parseFloat(prediction.prediction.lowRange))}–${money(parseFloat(prediction.prediction.highRange))} (${prediction.confidence}% confidence)`,
    support:         ind?.support?.length    ? ind.support.map(s => money(s)).join(', ')    : 'N/A',
    resistance:      ind?.resistance?.length ? ind.resistance.map(r => money(r)).join(', ') : 'N/A',
    fibonacci:       fibStr,
    moving_averages: maStr,
    macd:            macdStr,
    bollinger:       bbStr,
    atr_14:          ind?.atr_14 != null ? money(ind.atr_14) : 'N/A',
    regime:          prediction.regime?.regime
                       ? `${prediction.regime.regime} (${Math.round((prediction.regime.confidence ?? 0) * 100)}% conf)`
                       : 'N/A',
    jury_summary:    prediction.juryAnalysts
                       ?.map(a => `${a.id}: ${a.rating} (${a.confidence}%)`)
                       .join(', '),
    sentiment_label: prediction.sentiment?.label ?? 'Neutral',
    headlines:       prediction.news?.slice(0, 3).map(n => n.title).join(' | '),
  };
}

interface Props {
  prediction:   PredictionData | null;
  isDark:       boolean;
  primaryColor: string;
  open:         boolean;
  onClose:      () => void;
}

export default function StockChatPanel({ prediction, isDark, primaryColor, open, onClose }: Props) {
  const { session } = useAuth();
  const [messages,  setMessages]  = useState<ChatMessage[]>([]);
  const [input,     setInput]     = useState('');
  const [streaming, setStreaming] = useState(false);
  const bottomRef  = useRef<HTMLDivElement>(null);
  const abortRef   = useRef<AbortController | null>(null);

  // Abort any in-flight stream on unmount
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Remove a trailing empty assistant placeholder left by aborted/errored fetches
  const removeTrailingPlaceholder = () => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      return last?.role === 'assistant' && last.content === '' ? prev.slice(0, -1) : prev;
    });
  };

  const sendMessage = async (text: string) => {
    if (!text.trim() || streaming || !prediction) return;

    // Abort any previous in-flight stream before starting a new one
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const history = messages;
    setMessages(prev => [
      ...prev,
      { role: 'user',      content: text },
      { role: 'assistant', content: '' },
    ]);
    setInput('');
    setStreaming(true);

    const authHeaders: Record<string, string> = session?.access_token
      ? { Authorization: `Bearer ${session.access_token}` }
      : {};

    try {
      const response = await fetch('/api/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body:    JSON.stringify({ message: text, context: buildContext(prediction), history }),
        signal:  controller.signal,
      });

      if (!response.body) {
        removeTrailingPlaceholder();
        setStreaming(false);
        return;
      }

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data === '[DONE]') {
            setStreaming(false);
            return;
          }
          if (data.startsWith('[ERROR]')) {
            removeTrailingPlaceholder();
            setStreaming(false);
            return;
          }
          try {
            const token: string = JSON.parse(data);
            setMessages(prev => {
              const updated = [...prev];
              const last    = updated[updated.length - 1];
              if (last?.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content: last.content + token };
              }
              return updated;
            });
          } catch { /* non-JSON SSE line, skip */ }
        }
      }
    } catch (err: unknown) {
      // AbortError = intentional cancel; don't leave a blank bubble for other errors
      if ((err as { name?: string })?.name !== 'AbortError') {
        removeTrailingPlaceholder();
      }
    }

    setStreaming(false);
  };

  const bgPaper = isDark ? 'rgba(5,10,16,0.97)' : 'rgba(248,250,252,0.97)';

  return (
    <Drawer
      anchor="right"
      open={open}
      variant="persistent"
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 380 },
          maxWidth: '100vw',
          // On mobile the persistent drawer renders inline (no portal), so the
          // fixed bottom nav (60px, z1200) paints over its lower edge — hiding
          // the input. Trim the paper height to sit above the nav; the drawer
          // (z1200 default) still covers the watchlist chip bar (z1199) beneath.
          height: { xs: 'calc(100% - 60px)', sm: '100%' },
          background: bgPaper,
          backdropFilter: 'blur(20px)',
          borderLeft: `1px solid ${primaryColor}22`,
          display: 'flex',
          flexDirection: 'column',
        },
      }}
    >
      {/* Header */}
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ p: 2, borderBottom: `1px solid ${primaryColor}18`, flexShrink: 0 }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <MessageCircle size={16} color={primaryColor} />
          <Typography sx={{ fontWeight: 700, fontSize: '0.9rem' }}>
            AI Chat{prediction ? ` · ${prediction.symbol}` : ''}
          </Typography>
        </Stack>
        <IconButton size="small" onClick={onClose} aria-label="Close chat">
          <X size={16} />
        </IconButton>
      </Stack>

      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
        {messages.length === 0 ? (
          <Box>
            <Typography sx={{ fontSize: '0.78rem', opacity: 0.5, mb: 2, textAlign: 'center' }}>
              Your assistant for {prediction?.symbol ?? 'this stock'} — ask about its forecast,
              indicators, analyst jury, sentiment, or risks. It only covers this stock&apos;s analysis,
              not general web search.
            </Typography>
            <Stack spacing={1}>
              {BEGINNER_CHIPS.map(chip => (
                <Chip
                  key={chip}
                  label={chip}
                  disabled={!prediction}
                  onClick={() => sendMessage(chip)}
                  sx={{
                    cursor: prediction ? 'pointer' : 'default',
                    fontSize: '0.72rem',
                    height: 'auto',
                    py: 0.75,
                    justifyContent: 'flex-start',
                    background: `${primaryColor}0f`,
                    border: `1px solid ${primaryColor}28`,
                    color: 'text.primary',
                    '& .MuiChip-label': { whiteSpace: 'normal', lineHeight: 1.4 },
                    '&:hover': { background: prediction ? `${primaryColor}1f` : `${primaryColor}0f` },
                  }}
                />
              ))}
            </Stack>
          </Box>
        ) : (
          <Stack spacing={1.5}>
            {messages.map((msg, i) => (
              <Box
                key={i}
                sx={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}
              >
                <Box
                  sx={{
                    maxWidth: '85%',
                    px: 1.5,
                    py: 1,
                    borderRadius: msg.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                    background: msg.role === 'user'
                      ? `${primaryColor}dd`
                      : isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)',
                    color: msg.role === 'user' ? '#000' : 'text.primary',
                  }}
                >
                  <Typography sx={{ fontSize: '0.82rem', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                    {msg.content}
                    {streaming && i === messages.length - 1 && msg.role === 'assistant' && (
                      <Box
                        component="span"
                        sx={{
                          display: 'inline-block',
                          width: '2px',
                          height: '1em',
                          background: primaryColor,
                          ml: 0.25,
                          verticalAlign: 'text-bottom',
                          '@keyframes blink': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0 } },
                          animation: 'blink 1s step-end infinite',
                        }}
                      />
                    )}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Stack>
        )}
        <div ref={bottomRef} />
      </Box>

      {/* Input */}
      <Box sx={{ p: 1.5, borderTop: `1px solid ${primaryColor}18`, flexShrink: 0 }}>
        <Stack direction="row" spacing={1} alignItems="flex-end">
          <TextField
            fullWidth
            multiline
            maxRows={3}
            size="small"
            placeholder={`Ask about ${prediction?.symbol ?? 'this stock'}…`}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(input);
              }
            }}
            disabled={streaming || !prediction}
            sx={{ '& .MuiOutlinedInput-root': { borderRadius: 3, fontSize: '0.82rem' } }}
          />
          <Button
            variant="contained"
            size="small"
            aria-label="Send message"
            disabled={streaming || !input.trim() || !prediction}
            onClick={() => sendMessage(input)}
            sx={{
              minWidth: 40, height: 40, borderRadius: 2, p: 0,
              background: primaryColor,
              '&:hover': { background: primaryColor },
              '&.Mui-disabled': { background: `${primaryColor}44` },
            }}
          >
            <Send size={16} color="#000" />
          </Button>
        </Stack>
      </Box>
    </Drawer>
  );
}
