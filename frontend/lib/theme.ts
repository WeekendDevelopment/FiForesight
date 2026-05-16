import { createTheme } from '@mui/material';

export function buildTheme(mode: 'dark' | 'light') {
  return createTheme({
    palette: {
      mode,
      primary:   { main: mode === 'dark' ? '#f92aad' : '#0077ff' },
      secondary: { main: mode === 'dark' ? '#2de2e6' : '#7c3aed' },
      success:   { main: mode === 'dark' ? '#00ffa3' : '#16a34a' },
      error:     { main: mode === 'dark' ? '#ff0055' : '#dc2626' },
      background: {
        default: mode === 'dark' ? '#1a1b2e' : '#f0f4f8',
        paper:   mode === 'dark' ? '#1e1f3a' : '#ffffff',
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
              : '1px solid rgba(0, 119, 255, 0.15)',
            transition: 'all 0.3s ease',
            '&:hover': {
              border: mode === 'dark'
                ? '1px solid rgba(249, 42, 173, 0.4)'
                : '1px solid rgba(0, 119, 255, 0.4)',
            },
          },
        },
      },
    },
  });
}
