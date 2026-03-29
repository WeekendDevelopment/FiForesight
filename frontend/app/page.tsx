"use client";

import React, { useState, useMemo } from 'react';
import axios from 'axios';
import { 
  Box, Container, Typography, TextField, Button, Card, CardContent, 
  Grid, Divider, CircularProgress, Alert, ThemeProvider, createTheme, 
  CssBaseline, Paper, Chip, Stack
} from '@mui/material';
import { 
  TrendingUp, TrendingDown, Search, BrainCircuit, Activity, Clock
} from 'lucide-react';
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area
} from 'recharts';

interface PredictionData {
  symbol: string;
  currentPrice: string;
  rsi: string;
  prediction: {
    highRange: string;
    lowRange: string;
    trend: 'Bullish' | 'Bearish';
  };
  analystNote: string;
  confidence: 'low' | 'medium' | 'high';
  history: { date: string; price: number }[];
  lastUpdated: string;
}

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#6366f1' },
    secondary: { main: '#ec4899' },
    success: { main: '#22c55e' },
    error: { main: '#ef4444' },
    background: { default: '#0f172a', paper: '#1e293b' },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontWeight: 900 },
    h2: { fontWeight: 800 },
    h4: { fontWeight: 700 },
  },
  shape: { borderRadius: 16 },
});

export default function Dashboard() {
  const [symbol, setSymbol] = useState('SPY');
  const [prediction, setPrediction] = useState<PredictionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.post('/api/predict', { data: symbol });
      setPrediction(response.data);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Market analysis failed.');
    } finally {
      setLoading(false);
    }
  };

  const rsiInfo = useMemo(() => {
    if (!prediction) return null;
    const val = parseFloat(prediction.rsi);
    if (val >= 70) return { label: 'Overbought', color: 'error' as const };
    if (val <= 30) return { label: 'Oversold', color: 'success' as const };
    return { label: 'Neutral', color: 'secondary' as const };
  }, [prediction]);

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', py: 6, px: 2 }}>
        <Container maxWidth="lg">
          
          {/* Header & Search */}
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems="center" spacing={4} sx={{ mb: 8 }}>
            <Box>
              <Typography variant="h4" component="h1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Box sx={{ color: 'primary.main', display: 'flex' }}><BrainCircuit size={40} /></Box>
                FiForesight <Box component="span" sx={{ color: 'primary.main' }}>AI</Box>
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.6, letterSpacing: 1 }}>
                NEXT-GEN QUANTITATIVE FORECASTING
              </Typography>
            </Box>

            <Paper sx={{ p: 1, display: 'flex', alignItems: 'center', width: { xs: '100%', md: 400 }, background: 'rgba(255,255,255,0.05)', backdropFilter: 'blur(10px)' }}>
              <TextField
                fullWidth
                placeholder="Enter Ticker (e.g. NVDA)"
                variant="standard"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                InputProps={{ disableUnderline: true, sx: { px: 2, fontWeight: 700, fontSize: '1.1rem' } }}
              />
              <Button 
                variant="contained" 
                onClick={handlePredict} 
                disabled={loading}
                sx={{ borderRadius: 3, py: 1 }}
              >
                {loading ? <CircularProgress size={24} color="inherit" /> : <Search size={20} />}
              </Button>
            </Paper>
          </Stack>

          {error && <Alert severity="error" sx={{ mb: 4, borderRadius: 4 }}>{error}</Alert>}

          {prediction && (
            <Grid container spacing={4}>
              
              {/* Main Overview Card */}
              <Grid item xs={12} md={8}>
                <Card sx={{ height: '100%', border: '1px solid rgba(255,255,255,0.1)' }}>
                  <CardContent sx={{ p: 4 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', mb: 4 }}>
                      <Box>
                        <Typography variant="h2">{prediction.symbol}</Typography>
                        <Chip 
                          icon={prediction.prediction.trend === 'Bullish' ? <TrendingUp size={16}/> : <TrendingDown size={16}/>}
                          label={`${prediction.prediction.trend} Trend`} 
                          color={prediction.prediction.trend === 'Bullish' ? 'success' : 'error'}
                          sx={{ fontWeight: 800, mt: 1 }}
                        />
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="h4" color="primary">${prediction.currentPrice}</Typography>
                        <Typography variant="caption" sx={{ opacity: 0.5 }}>LATEST CLOSE</Typography>
                      </Box>
                    </Box>

                    {/* Price History Chart */}
                    <Box sx={{ height: 300, width: '100%', mt: 4 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={prediction.history}>
                          <defs>
                            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                              <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                          <XAxis dataKey="date" stroke="rgba(255,255,255,0.3)" fontSize={12} tickLine={false} />
                          <YAxis domain={['auto', 'auto']} hide />
                          <Tooltip 
                            contentStyle={{ backgroundColor: '#1e293b', borderRadius: '12px', border: 'none' }}
                            itemStyle={{ color: '#fff' }}
                          />
                          <Area type="monotone" dataKey="price" stroke="#6366f1" strokeWidth={3} fillOpacity={1} fill="url(#colorPrice)" />
                        </AreaChart>
                      </ResponsiveContainer>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Side Stats */}
              <Grid item xs={12} md={4}>
                <Stack spacing={4}>
                  <Card sx={{ background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)' }}>
                    <CardContent sx={{ p: 3 }}>
                      <Typography variant="overline" sx={{ opacity: 0.5, fontWeight: 900 }}>48H Forecast Range</Typography>
                      <Stack spacing={2} sx={{ mt: 2 }}>
                        <Box>
                          <Typography variant="h4" color="success.main" sx={{ fontWeight: 900 }}>${prediction.prediction.highRange}</Typography>
                          <Typography variant="caption">EXPECTED HIGH</Typography>
                        </Box>
                        <Divider sx={{ opacity: 0.1 }} />
                        <Box>
                          <Typography variant="h4" color="error.main" sx={{ fontWeight: 900 }}>${prediction.prediction.lowRange}</Typography>
                          <Typography variant="caption">EXPECTED LOW</Typography>
                        </Box>
                      </Stack>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardContent sx={{ p: 3 }}>
                      <Stack direction="row" justifyContent="space-between">
                        <Box>
                          <Typography variant="overline" sx={{ opacity: 0.5, fontWeight: 900 }}>RSI (Daily)</Typography>
                          <Typography variant="h4" sx={{ fontWeight: 900 }}>{prediction.rsi}</Typography>
                        </Box>
                        <Chip label={rsiInfo?.label} color={rsiInfo?.color} size="small" />
                      </Stack>
                    </CardContent>
                  </Card>

                  <Card sx={{ background: 'rgba(99, 102, 241, 0.05)', border: '1px dashed rgba(99, 102, 241, 0.3)' }}>
                    <CardContent sx={{ p: 3 }}>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                        <Box sx={{ color: 'primary.main', display: 'flex' }}><BrainCircuit size={16} /></Box>
                        <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main' }}>AI Analyst Note</Typography>
                      </Stack>
                      <Typography variant="body2" sx={{ fontStyle: 'italic', lineHeight: 1.6 }}>
                        "{prediction.analystNote}"
                      </Typography>
                      <Box sx={{ mt: 2 }}>
                        <Typography variant="caption" sx={{ opacity: 0.4 }}>CONFIDENCE: {prediction.confidence?.toUpperCase()}</Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Stack>
              </Grid>

              {/* Footer Meta */}
              <Grid item xs={12}>
                <Stack direction="row" justifyContent="center" spacing={4} sx={{ opacity: 0.3, mt: 4 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Activity size={14} />
                    <Typography variant="caption">REAL-TIME FEED</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Clock size={14} />
                    <Typography variant="caption">{new Date(prediction.lastUpdated).toLocaleTimeString()}</Typography>
                  </Box>
                </Stack>
              </Grid>

            </Grid>
          )}
        </Container>
      </Box>
    </ThemeProvider>
  );
}
