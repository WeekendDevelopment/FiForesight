'use client';

import { useState } from 'react';
import {
  Autocomplete, Box, Button, Container, Paper, Stack,
  TextField, Typography,
} from '@mui/material';
import { BarChart2, Search } from 'lucide-react';
import { useAppShell } from '../../../contexts/AppShellContext';
import OptionsChainPanel from '../../../components/OptionsChainPanel';
// Shared ticker suggestion source (lib/tickerSearch.ts) — also feeds the
// analysis page Autocomplete and the Ctrl+K command palette (Feature 33).
import { POPULAR_TICKERS } from '../../../lib/tickerSearch';

export default function OptionsPage() {
  const { isDark, primaryColor } = useAppShell();
  const [input,          setInput]          = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState('');

  const submit = () => {
    const sym = input.trim().toUpperCase();
    if (sym) setSelectedSymbol(sym);
  };

  return (
    <Container maxWidth="lg" disableGutters>
      {/* Heading */}
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.5 }}>
        <BarChart2 size={26} color={primaryColor} />
        <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
          Options Chain
        </Typography>
      </Stack>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Look up the live options chain for any ticker — Greeks, IV skew, and put/call ratio.
      </Typography>

      {/* Symbol search */}
      <Paper
        sx={{
          p: 0.5, mb: 4, display: 'flex', gap: 1, alignItems: 'center',
          width: { xs: '100%', md: 480 },
          background: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)',
          backdropFilter: 'blur(20px)', borderRadius: 4,
        }}
      >
        <Autocomplete
          freeSolo
          options={POPULAR_TICKERS}
          inputValue={input}
          onInputChange={(_, v) => setInput(v.toUpperCase())}
          onChange={(_, v) => v && setSelectedSymbol(String(v).toUpperCase())}
          sx={{ flexGrow: 1 }}
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder="Search Ticker…"
              variant="standard"
              onKeyDown={e => e.key === 'Enter' && submit()}
              InputProps={{ ...params.InputProps, disableUnderline: true, sx: { px: 2, fontWeight: 700 } }}
            />
          )}
        />
        <Button
          variant="contained"
          onClick={submit}
          sx={{ borderRadius: 3, minWidth: 50, py: 1, boxShadow: `0 0 20px ${primaryColor}4d` }}
        >
          <Search size={20} />
        </Button>
      </Paper>

      {/* Chain or empty state */}
      {selectedSymbol ? (
        <Box sx={{ maxWidth: 760 }}>
          <OptionsChainPanel
            key={selectedSymbol}
            symbol={selectedSymbol}
            isDark={isDark}
            primaryColor={primaryColor}
          />
        </Box>
      ) : (
        <Box sx={{
          height: '45vh', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 2, opacity: 0.2,
        }}>
          <BarChart2 size={52} color={primaryColor} />
          <Typography variant="h6" sx={{ fontWeight: 300, letterSpacing: 2 }}>
            Enter a ticker to load its options chain
          </Typography>
        </Box>
      )}
    </Container>
  );
}
