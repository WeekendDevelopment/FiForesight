import { createTheme } from '@mui/material';

export function buildTheme(mode: 'dark' | 'light') {
  return createTheme({
    palette: {
      mode,
      primary:   { main: mode === 'dark' ? '#00f2ff' : '#0077ff' },
      secondary: { main: mode === 'dark' ? '#bc13fe' : '#7c3aed' },
      success:   { main: mode === 'dark' ? '#00ffa3' : '#16a34a' },
      error:     { main: mode === 'dark' ? '#ff0055' : '#dc2626' },
      background: {
        default: mode === 'dark' ? '#050a10' : '#f0f4f8',
        paper:   mode === 'dark' ? '#0d1520' : '#ffffff',
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
              ? '1px solid rgba(0, 242, 255, 0.1)'
              : '1px solid rgba(0, 119, 255, 0.15)',
            transition: 'all 0.3s ease',
            '&:hover': {
              border: mode === 'dark'
                ? '1px solid rgba(0, 242, 255, 0.3)'
                : '1px solid rgba(0, 119, 255, 0.4)',
            },
          },
        },
      },
    },
  });
}
