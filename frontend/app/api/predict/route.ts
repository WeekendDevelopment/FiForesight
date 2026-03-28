import { NextResponse } from 'next/server';
import axios from 'axios';
import { cleanAndIngest, queryMarketData, queryEarningsData } from '@/lib/influx';

const ALPHA_VANTAGE_API_KEY = process.env.ALPHA_VANTAGE_API_KEY;

// Utility function to handle API rate limiting
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Calculates the Relative Strength Index (RSI) for a series of prices.
 */
function calculateRSI(prices: number[], period: number = 14): number {
  if (prices.length <= period) return 50; // Default if not enough data

  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i++) {
    const change = prices[i] - prices[i - 1];
    if (change > 0) gains += change;
    else losses -= change;
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

export async function POST(request: Request) {
  let symbol: string;
  let requestBody: any;

  try {
    requestBody = await request.json();
    symbol = (requestBody.data || 'SPY').toUpperCase();
  } catch (jsonError: any) {
    console.error('JSON parsing error:', jsonError);
    return NextResponse.json({ error: 'Invalid request body. Expected JSON.' }, { status: 400 });
  }

  if (!ALPHA_VANTAGE_API_KEY) {
    return NextResponse.json({ 
      error: 'Alpha Vantage API Key is missing. Please add it to your .env.local file.' 
    }, { status: 500 });
  }

  try {
    console.log(`Fetching data for: ${symbol}`);

    // 1. Fetch Fresh Data from Alpha Vantage
    const historicalResponse = await axios.get(`https://www.alphavantage.co/query`, {
      params: {
        function: 'TIME_SERIES_MONTHLY_ADJUSTED',
        symbol: symbol,
        apikey: ALPHA_VANTAGE_API_KEY
      }
    });

    await sleep(2000); // Respect rate limit

    const earningsResponse = await axios.get(`https://www.alphavantage.co/query`, {
      params: {
        function: 'EARNINGS',
        symbol: symbol,
        apikey: ALPHA_VANTAGE_API_KEY
      }
    });

    const monthlySeries = historicalResponse.data['Monthly Adjusted Time Series'];
    if (!monthlySeries) {
      const note = historicalResponse.data['Note'] || earningsResponse.data['Note'];
      if (note) return NextResponse.json({ error: 'API Rate Limit Reached.' }, { status: 429 });
      return NextResponse.json({ error: `Could not find data for ${symbol}.` }, { status: 400 });
    }

    // 2. Ingest to InfluxDB
    try {
      await cleanAndIngest(symbol, historicalResponse.data, earningsResponse.data);
    } catch (ingestError) {
      console.warn('Ingestion failed:', ingestError);
    }

    // 3. Query Historical Data Back for AI Features
    const historicalPrices = await queryMarketData(symbol, '-2y');
    const earningsHistory = await queryEarningsData(symbol, '-5y');

    // 4. Calculate AI Features (RSI, etc.)
    const closes = historicalPrices.map((row: any) => row.close);
    const rsi = calculateRSI(closes);

    // 5. Prediction Logic (Enhanced with RSI and Earnings)
    const lastMonthDate = Object.keys(monthlySeries)[0];
    const lastMonthData = monthlySeries[lastMonthDate];
    const currentPrice = parseFloat(lastMonthData['4. close']);
    const high = parseFloat(lastMonthData['2. high']);
    const low = parseFloat(lastMonthData['3. low']);

    const volatility = (high - low) / 20;
    
    // AI Adjustment based on RSI (Overbought/Oversold)
    let bias = 1.0;
    if (rsi > 70) bias = 0.8; // Overbought, expect smaller gains
    if (rsi < 30) bias = 1.2; // Oversold, expect stronger bounce

    const predictedHigh = currentPrice + (volatility * 0.5 * bias);
    const predictedLow = currentPrice - (volatility * 0.5 * (2 - bias));

    return NextResponse.json({
      symbol,
      currentPrice: currentPrice.toFixed(2),
      rsi: rsi.toFixed(2),
      prediction: {
        highRange: predictedHigh.toFixed(2),
        lowRange: predictedLow.toFixed(2),
        trend: rsi > 50 ? 'Bullish' : 'Bearish'
      },
      lastUpdated: new Date().toISOString(),
      historicalContext: historicalPrices.length,
      earningsHistory: earningsHistory.length
    });

  } catch (error: any) {
    console.error('Prediction Error:', error);
    return NextResponse.json({ error: 'Failed to generate prediction.' }, { status: 500 });
  }
}
