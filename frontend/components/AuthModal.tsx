'use client';

import { useState } from 'react';
import {
  Dialog, DialogContent, DialogTitle, TextField, Button,
  Tab, Tabs, Box, Alert, CircularProgress,
} from '@mui/material';
import { supabase } from '../lib/supabase';

interface Props {
  open:    boolean;
  onClose: () => void;
}

export default function AuthModal({ open, onClose }: Props) {
  const [tab,      setTab]      = useState<0 | 1>(0); // 0=login 1=signup
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [message,  setMessage]  = useState<string | null>(null);

  const reset = () => { setError(null); setMessage(null); setEmail(''); setPassword(''); };

  const handleTabChange = (_: React.SyntheticEvent, v: number) => {
    setTab(v as 0 | 1);
    reset();
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      if (tab === 0) {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        onClose();
      } else {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setMessage('Check your email to confirm your account.');
      }
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Auth error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pb: 0 }}>FiForesight Account</DialogTitle>
      <DialogContent>
        <Tabs value={tab} onChange={handleTabChange} sx={{ mb: 2 }}>
          <Tab label="Sign In" />
          <Tab label="Sign Up" />
        </Tabs>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          <TextField
            label="Email" type="email" size="small" fullWidth
            value={email} onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
          />
          <TextField
            label="Password" type="password" size="small" fullWidth
            value={password} onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
          />
          {error   && <Alert severity="error"   sx={{ py: 0 }}>{error}</Alert>}
          {message && <Alert severity="success" sx={{ py: 0 }}>{message}</Alert>}
          <Button
            variant="contained" fullWidth onClick={handleSubmit}
            disabled={loading || !email || !password}
            startIcon={loading ? <CircularProgress size={14} /> : undefined}
          >
            {tab === 0 ? 'Sign In' : 'Create Account'}
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
