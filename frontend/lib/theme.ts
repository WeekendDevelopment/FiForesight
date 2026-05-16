import { createTheme } from '@mui/material';

export function buildTheme(mode: 'dark' | 'light') {
  return createTheme({
    palette: {
      mode,
      primary:   { main: mode === 'dark' ? '#f92aad' : '#1e3a8a' },
      secondary: { main: mode === 'dark' ? '#2de2e6' : '#6d28d9' },
      success:   { main: mode === 'dark' ? '#00ffa3' : '#15803d' },
      error:     { main: mode === 'dark' ? '#ff0055' : '#b91c1c' },
      background: {
        default: mode === 'dark' ? '#1a1b2e' : '#f2f0eb',
        paper:   mode === 'dark' ? '#1e1f3a' : '#fdfcf9',
      },
    },
    typography: {
      fontFamily: '"Inter", "Roboto", sans-serif',
      h1: { fontWeight: 900, letterSpacing: '-0.05em' },
      h2: { fontWeight: 800, letterSpacing: '-0.03em' },
      h4: { fontWeight: 700 },
    },
    shape: { borderRadius: 12 },
    components: {
      MuiCard: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            border: mode === 'dark'
              ? '1px solid rgba(249, 42, 173, 0.15)'
              : '1px solid rgba(30, 58, 138, 0.12)',
            transition: 'all 0.3s ease',
            '&:hover': {
              border: mode === 'dark'
                ? '1px solid rgba(249, 42, 173, 0.4)'
                : '1px solid rgba(30, 58, 138, 0.35)',
            },
          },
        },
      },
    },
  });
}
