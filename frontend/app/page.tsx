"use client";

import { useState } from 'react';
import axios from 'axios';

interface PredictionData {
  symbol: string;
  currentPrice: string;
  rsi: string;
  prediction: {
    highRange: string;
    lowRange: string;
    trend: 'Bullish' | 'Bearish';
  };
  lastUpdated: string;
  historicalContext: number;
  earningsHistory: number;
}

export default function Home() {
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
    } catch (error: any) {
      console.error('Error fetching prediction', error);
      setError(error.response?.data?.error || 'Failed to fetch prediction');
    } finally {
      setLoading(false);
    }
  };

  const getRSILabel = (rsi: number) => {
    if (rsi >= 70) return { text: 'Overbought', color: 'text-error' };
    if (rsi <= 30) return { text: 'Oversold', color: 'text-success' };
    return { text: 'Neutral', color: 'text-secondary' };
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-base-200">
      <div className="card w-full max-w-lg bg-base-100 shadow-xl">
        <div className="card-body">
          <h1 className="card-title text-3xl font-bold mb-4">Financial Forecasting</h1>
          <p className="mb-6 opacity-70 text-sm">AI-driven market analysis using technical indicators and historical earnings patterns.</p>
          
          <div className="form-control">
            <label className="label">
              <span className="label-text font-semibold">Ticker Symbol</span>
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="input input-bordered flex-grow"
                placeholder="e.g., SPY, AAPL"
              />
              <button 
                onClick={handlePredict} 
                className={`btn btn-primary ${loading ? 'loading' : ''}`}
                disabled={loading}
              >
                {loading ? 'Analyzing...' : 'Analyze'}
              </button>
            </div>
          </div>

          {error && (
            <div className="alert alert-error mt-4 text-sm py-2">
              <span>{error}</span>
            </div>
          )}

          {prediction && (
            <div className="mt-8 space-y-6">
              <div className="flex justify-between items-center">
                <span className="text-3xl font-extrabold">{prediction.symbol}</span>
                <span className={`badge badge-lg py-4 font-bold ${prediction.prediction.trend === 'Bullish' ? 'badge-success' : 'badge-error'}`}>
                  {prediction.prediction.trend} Trend
                </span>
              </div>
              
              <div className="grid grid-cols-1 gap-4">
                <div className="bg-base-200 p-6 rounded-2xl">
                  <p className="text-xs uppercase opacity-50 font-bold mb-1">Current Price</p>
                  <p className="text-4xl font-mono">${prediction.currentPrice}</p>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-success/10 p-4 rounded-2xl border border-success/20">
                    <p className="text-[10px] uppercase text-success font-bold mb-1 tracking-tighter">Expected High (48h)</p>
                    <p className="text-2xl font-mono text-success">${prediction.prediction.highRange}</p>
                  </div>
                  <div className="bg-error/10 p-4 rounded-2xl border border-error/20">
                    <p className="text-[10px] uppercase text-error font-bold mb-1 tracking-tighter">Expected Low (48h)</p>
                    <p className="text-2xl font-mono text-error">${prediction.prediction.lowRange}</p>
                  </div>
                </div>
              </div>

              <div className="divider text-[10px] uppercase opacity-30 tracking-[0.2em]">Technical Indicators</div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-base-200 p-4 rounded-2xl flex flex-col items-center">
                  <p className="text-xs uppercase opacity-50 font-bold mb-2">RSI (14-Month)</p>
                  <p className={`text-3xl font-mono font-bold ${getRSILabel(parseFloat(prediction.rsi)).color}`}>
                    {prediction.rsi}
                  </p>
                  <p className="text-[10px] mt-1 font-bold uppercase opacity-70">
                    {getRSILabel(parseFloat(prediction.rsi)).text}
                  </p>
                </div>
                
                <div className="bg-base-200 p-4 rounded-2xl flex flex-col items-center justify-center">
                  <div className="text-center">
                    <p className="text-xs uppercase opacity-50 font-bold mb-1">InfluxDB Context</p>
                    <p className="text-xl font-mono">{prediction.historicalContext} <span className="text-[10px]">Points</span></p>
                    <p className="text-[8px] uppercase opacity-40 mt-1">{prediction.earningsHistory} Earnings Reports</p>
                  </div>
                </div>
              </div>
              
              <p className="text-[9px] mt-8 text-center opacity-40 uppercase tracking-[0.3em] font-medium">
                Data provided by Alpha Vantage • Analysis Completed at {new Date(prediction.lastUpdated).toLocaleTimeString()}
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}