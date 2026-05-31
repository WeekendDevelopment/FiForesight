'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import { Box, Paper, Typography, CircularProgress } from '@mui/material';

interface Level {
  price: number;
  size: number;
}

interface OrderBook {
  symbol: string;
  timestamp: string;
  mid_price: number;
  bids: Level[];
  asks: Level[];
  spread: number;
  spread_pct: number;
  bid_ask_imbalance: number;
  source?: string;
}

const POLL_MS = 3000;
const GREEN = '#16a34a';
const RED = '#dc2626';

function fmtPrice(v: number): string {
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtSize(v: number): string {
  return v.toLocaleString();
}

export default function OrderBookPanel({ symbol }: { symbol: string }) {
  const [book, setBook] = useState<OrderBook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchBook = useCallback(async () => {
    if (!symbol) return;
    try {
      const { data } = await axios.get<OrderBook>(`/api/orderbook/${symbol}`, { timeout: 10000 });
      setBook(data);
      setError(null);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
        'Order book unavailable';
      setError(msg);
      setBook(null);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    setBook(null);
    setError(null);
    fetchBook();
    timer.current = setInterval(fetchBook, POLL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [symbol, fetchBook]);

  if (!symbol) {
    return (
      <Paper sx={{ p: 2, borderRadius: 2 }}>
        <Typography variant="body2" color="text.secondary">
          Search a ticker to view its order book.
        </Typography>
      </Paper>
    );
  }

  if (error) {
    return (
      <Paper sx={{ p: 2, borderRadius: 2 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
          Order Book — {symbol.toUpperCase()}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {error}
        </Typography>
      </Paper>
    );
  }

  if (loading && !book) {
    return (
      <Paper sx={{ p: 2, borderRadius: 2, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress size={22} />
      </Paper>
    );
  }

  if (!book) return null;

  const asksDesc = [...book.asks].sort((a, b) => b.price - a.price); // highest ask on top
  const bidsDesc = [...book.bids].sort((a, b) => b.price - a.price); // best bid just below mid
  const maxSize = Math.max(
    1,
    ...book.bids.map((b) => b.size),
    ...book.asks.map((a) => a.size),
  );

  const bidPct = Math.round(book.bid_ask_imbalance * 100);
  const askPct = 100 - bidPct;

  const COLS = '1fr 88px 1fr';

  const Row = ({ level, side }: { level: Level; side: 'bid' | 'ask' }) => {
    const widthPct = `${Math.max(2, (level.size / maxSize) * 100)}%`;
    const color = side === 'bid' ? GREEN : RED;
    return (
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: COLS,
          alignItems: 'center',
          fontSize: 13,
          fontVariantNumeric: 'tabular-nums',
          py: '2px',
        }}
      >
        {/* Bid Size column (right-aligned green bar) */}
        <Box sx={{ position: 'relative', height: 22, textAlign: 'right', pr: 1 }}>
          {side === 'bid' && (
            <>
              <Box
                sx={{
                  position: 'absolute',
                  top: 0,
                  bottom: 0,
                  right: 0,
                  width: widthPct,
                  bgcolor: `${GREEN}26`,
                  borderRadius: '2px',
                }}
              />
              <Box sx={{ position: 'relative', lineHeight: '22px' }}>{fmtSize(level.size)}</Box>
            </>
          )}
        </Box>

        {/* Price column (centre) */}
        <Box
          sx={{
            textAlign: 'center',
            fontWeight: 600,
            color,
            lineHeight: '22px',
          }}
        >
          {fmtPrice(level.price)}
        </Box>

        {/* Ask Size column (left-aligned red bar) */}
        <Box sx={{ position: 'relative', height: 22, textAlign: 'left', pl: 1 }}>
          {side === 'ask' && (
            <>
              <Box
                sx={{
                  position: 'absolute',
                  top: 0,
                  bottom: 0,
                  left: 0,
                  width: widthPct,
                  bgcolor: `${RED}26`,
                  borderRadius: '2px',
                }}
              />
              <Box sx={{ position: 'relative', lineHeight: '22px' }}>{fmtSize(level.size)}</Box>
            </>
          )}
        </Box>
      </Box>
    );
  };

  return (
    <Paper sx={{ p: 2, borderRadius: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Order Book — {book.symbol}
          </Typography>
          {book.source && (
            <Typography
              variant="caption"
              sx={{
                px: 0.75,
                py: '1px',
                borderRadius: 1,
                bgcolor: 'action.hover',
                color: 'text.secondary',
                fontSize: 10,
                whiteSpace: 'nowrap',
              }}
            >
              {book.source}
            </Typography>
          )}
        </Box>
        <Typography variant="caption" color="text.secondary">
          spread {fmtPrice(book.spread)} ({book.spread_pct.toFixed(3)}%)
        </Typography>
      </Box>

      {/* Column headers */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: COLS,
          fontSize: 11,
          color: 'text.secondary',
          textTransform: 'uppercase',
          letterSpacing: 0.4,
          mb: 0.5,
        }}
      >
        <Box sx={{ textAlign: 'right', pr: 1 }}>Bid Size</Box>
        <Box sx={{ textAlign: 'center' }}>Price</Box>
        <Box sx={{ textAlign: 'left', pl: 1 }}>Ask Size</Box>
      </Box>

      {/* Asks (top) */}
      {asksDesc.map((lvl, i) => (
        <Row key={`a-${i}`} level={lvl} side="ask" />
      ))}

      {/* Mid-price divider */}
      <Box
        sx={{
          my: 0.75,
          py: 0.5,
          textAlign: 'center',
          borderTop: '1px dashed',
          borderBottom: '1px dashed',
          borderColor: 'divider',
        }}
      >
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {book.mid_price > 0 ? fmtPrice(book.mid_price) : '—'}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          mid price
        </Typography>
      </Box>

      {/* Bids (bottom) */}
      {bidsDesc.map((lvl, i) => (
        <Row key={`b-${i}`} level={lvl} side="bid" />
      ))}

      {/* Imbalance meter */}
      <Box sx={{ mt: 1.5 }}>
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: 11,
            color: 'text.secondary',
            mb: 0.5,
          }}
        >
          <span style={{ color: GREEN }}>Bid {bidPct}%</span>
          <span>Imbalance</span>
          <span style={{ color: RED }}>Ask {askPct}%</span>
        </Box>
        <Box sx={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden' }}>
          <Box sx={{ width: `${bidPct}%`, bgcolor: GREEN }} />
          <Box sx={{ width: `${askPct}%`, bgcolor: RED }} />
        </Box>
      </Box>
    </Paper>
  );
}
