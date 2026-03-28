import { NextResponse } from 'next/server';
import axios from 'axios';
import { cleanAndIngest, queryMarketData, queryEarningsData } from '../../../lib/influx';
import { generatePrediction } from '../../../lib/gemini';

const ALPHA_VANTAGE_API_KEY = process.env.ALPHA_VANTAGE_API_KEY;

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export async function POST(request: Request) {
  let symbol: string;
  try {
    const body = await request.json();
    symbol = (body.data || 'SPY').toUpperCase();
  } catch (e) {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }

  try {
    console.log(`Analyzing: ${symbol}`);

    // 1. Try to Fetch Fresh Data
    try {
      const histRes = await axios.get(`https://www.alphavantage.co/query`, {
        params: { function: 'TIME_SERIES_MONTHLY_ADJUSTED', symbol, apikey: ALPHA_VANTAGE_API_KEY }
      });

      if (!histRes.data['Note']) {
        await sleep(1500);
        const earnRes = await axios.get(`https://www.alphavantage.co/query`, {
          params: { function: 'EARNINGS', symbol, apikey: ALPHA_VANTAGE_API_KEY }
        });
        await cleanAndIngest(symbol, histRes.data, earnRes.data);
      }
    } catch (apiError: any) {
      console.warn('API Limit or Error. Fallback to cache.');
    }

    // 2. Query Context
    const prices = await queryMarketData(symbol, '-2y');
    const earnings = await queryEarningsData(symbol, '-5y');

    if (prices.length === 0) {
      return NextResponse.json({ error: 'Data not found.' }, { status: 404 });
    }

    // 3. Tech Analysis
    const rsi = calculateRSI(prices.map((p: any) => p.close));

    // 4. AI Prediction
    const aiResult = await generatePrediction(symbol, prices, earnings, rsi);

    return NextResponse.json({
      symbol,
      currentPrice: prices[prices.length - 1]?.close.toFixed(2),
      rsi: rsi.toFixed(2),
      prediction: {
        highRange: aiResult.predictedHigh,
        lowRange: aiResult.predictedLow,
        trend: rsi > 50 ? 'Bullish' : 'Bearish'
      },
      analystNote: aiResult.analystNote,
      confidence: aiResult.confidence,
      history: prices.slice(-12).map(p => ({
        date: new Date(p._time).toLocaleDateString('en-US', { month: 'short' }),
        price: p.close
      })),
      lastUpdated: new Date().toISOString()
    });

  } catch (error: any) {
    console.error('Error:', error);
    return NextResponse.json({ error: 'System error' }, { status: 500 });
  }
}

function calculateRSI(prices: number[], period: number = 14): number {
  if (prices.length <= period) return 50;
  let gains = 0, losses = 0;
  for (let i = 1; i <= period; i++) {
    const change = prices[i] - prices[i - 1];
    if (change > 0) gains += change; else losses -= change;
  }
  let avgGain = gains / period, avgLoss = losses / period;
  for (let i = period + 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    const gain = change > 0 ? change : 0, loss = change < 0 ? -change : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
  }
  return 100 - (100 / (1 + avgGain / avgLoss));
}
