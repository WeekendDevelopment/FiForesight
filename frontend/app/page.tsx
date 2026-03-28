"use client";

import { useState } from 'react';
import axios from 'axios';

interface PredictionData {
  symbol: string;
  currentPrice: string;
  prediction: {
    highRange: string;
    lowRange: string;
    trend: 'Bullish' | 'Bearish';
  };
  lastUpdated: string;
}

export default function Home() {
  const [symbol, setSymbol] = useState('SPY'); // Default to SPY for Alpha Vantage
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

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-base-200">
      <div className="card w-full max-w-lg bg-base-100 shadow-xl">
        <div className="card-body">
          <h1 className="card-title text-3xl font-bold mb-4">Financial Forecasting</h1>
          <p className="mb-6 opacity-70 text-sm">Real-time market analysis for the next 48 hours using Alpha Vantage data.</p>
          
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
            <div className="mt-8">
              <div className="flex justify-between items-center mb-4">
                <span className="text-2xl font-bold">{prediction.symbol}</span>
                <span className={`badge badge-lg ${prediction.prediction.trend === 'Bullish' ? 'badge-success' : 'badge-error'}`}>
                  {prediction.prediction.trend}
                </span>
              </div>
              
              <div className="grid grid-cols-1 gap-4">
                <div className="bg-base-200 p-4 rounded-xl">
                  <p className="text-xs uppercase opacity-50 font-bold mb-1">Last Close</p>
                  <p className="text-3xl font-mono">${prediction.currentPrice}</p>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-success/10 p-4 rounded-xl border border-success/20">
                    <p className="text-xs uppercase text-success font-bold mb-1">Expected High</p>
                    <p className="text-xl font-mono text-success">${prediction.prediction.highRange}</p>
                  </div>
                  <div className="bg-error/10 p-4 rounded-xl border border-error/20">
                    <p className="text-xs uppercase text-error font-bold mb-1">Expected Low</p>
                    <p className="text-xl font-mono text-error">${prediction.prediction.lowRange}</p>
                  </div>
                </div>
              </div>
              
              <p className="text-[10px] mt-6 text-center opacity-40 uppercase tracking-widest">
                Data provided by Alpha Vantage • {new Date(prediction.lastUpdated).toLocaleTimeString()}
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}