'use client';

import { Box, Typography, Button, Paper } from '@mui/material';
import { Lock } from 'lucide-react';

interface AuthGateProps {
  title:      string;
  message:    string;
  onSignIn:   () => void;
  isDark:     boolean;
  primaryColor: string;
}

export default function AuthGate({ title, message, onSignIn, isDark, primaryColor }: AuthGateProps) {
  return (
    <Paper
      sx={{
        p: 4,
        textAlign: 'center',
        border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'}`,
        background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)',
        borderRadius: 3,
      }}
    >
      <Box sx={{ color: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)', mb: 2 }}>
        <Lock size={36} />
      </Box>
      <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        {message}
      </Typography>
      <Button
        variant="outlined"
        size="small"
        onClick={onSignIn}
        sx={{
          borderColor: `${primaryColor}77`,
          color: primaryColor,
          fontWeight: 700,
          '&:hover': { borderColor: primaryColor, background: `${primaryColor}12` },
        }}
      >
        Sign In
      </Button>
    </Paper>
  );
}
