'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Box, Button, Chip, Drawer, IconButton,
  Stack, TextField, Typography,
} from '@mui/material';
import { MessageCircle, Send, X } from 'lucide-react';
import type { ChatMessage, PredictionData } from '../types';

const BEGINNER_CHIPS = [
  "What does RSI mean for this stock?",
  "Is this a good entry point?",
  "What's the main risk here?",
  "Explain the analyst jury verdicts",
];

function buildContext(prediction: PredictionData) {
  return {
    symbol:         prediction.symbol,
    currentPrice:   prediction.currentPrice,
    rsi:            prediction.rsi,
    trend:          prediction.prediction.trend,
    jury_summary:   prediction.juryAnalysts
                      ?.map(a => `${a.id}: ${a.rating} (${a.confidence}%)`)
                      .join(', '),
    sentiment_label: prediction.analystNote?.slice(0, 100),
    headlines:      prediction.news?.slice(0, 3).map(n => n.title).join(' | '),
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
  const [messages,  setMessages]  = useState<ChatMessage[]>([]);
  const [input,     setInput]     = useState('');
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || streaming || !prediction) return;

    const history = messages;
    setMessages(prev => [
      ...prev,
      { role: 'user',      content: text },
      { role: 'assistant', content: '' },
    ]);
    setInput('');
    setStreaming(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          context: buildContext(prediction),
          history,
        }),
      });

      if (!response.body) { setStreaming(false); return; }

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
          if (data === '[DONE]' || data.startsWith('[ERROR]')) {
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
          } catch { /* non-JSON line, skip */ }
        }
      }
    } catch { /* network error */ }

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
          width: 380,
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
        <IconButton size="small" onClick={onClose}>
          <X size={16} />
        </IconButton>
      </Stack>

      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
        {messages.length === 0 ? (
          <Box>
            <Typography sx={{ fontSize: '0.78rem', opacity: 0.5, mb: 2, textAlign: 'center' }}>
              Ask anything about {prediction?.symbol ?? 'this stock'}
            </Typography>
            <Stack spacing={1}>
              {BEGINNER_CHIPS.map(chip => (
                <Chip
                  key={chip}
                  label={chip}
                  onClick={() => sendMessage(chip)}
                  sx={{
                    cursor: 'pointer',
                    fontSize: '0.72rem',
                    height: 'auto',
                    py: 0.75,
                    justifyContent: 'flex-start',
                    background: `${primaryColor}0f`,
                    border: `1px solid ${primaryColor}28`,
                    color: 'text.primary',
                    '& .MuiChip-label': { whiteSpace: 'normal', lineHeight: 1.4 },
                    '&:hover': { background: `${primaryColor}1f` },
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
            placeholder="Ask about this stock…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(input);
              }
            }}
            disabled={streaming}
            sx={{ '& .MuiOutlinedInput-root': { borderRadius: 3, fontSize: '0.82rem' } }}
          />
          <Button
            variant="contained"
            size="small"
            disabled={streaming || !input.trim()}
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
