import { NextResponse } from 'next/server';
import axios from 'axios';
import { cleanAndIngest, queryMarketData, queryEarningsData } from '../../../lib/influx';

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

  try {
    console.log(`Fetching quote for: ${symbol}`);
    
    // Using GLOBAL_QUOTE for real-time price info (usually very stable on free tier)
    const response = await axios.get(`http://localhost:8000/global-quote`, {
      params: {
        symbol: symbol
      }
    });

    await sleep(2000);

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

    try {
      await cleanAndIngest(symbol, historicalResponse.data, earningsResponse.data);
    } catch (ingestError) {
      console.warn('Ingestion failed:', ingestError);
    }

    const historicalPrices = await queryMarketData(symbol, '-2y');
    const earningsHistory = await queryEarningsData(symbol, '-5y');

    const closes = historicalPrices.map((row: any) => row.close);
    const rsi = calculateRSI(closes);

    const lastMonthDate = Object.keys(monthlySeries)[0];
    const lastMonthData = monthlySeries[lastMonthDate];
    const currentPrice = parseFloat(lastMonthData['4. close']);
    const high = parseFloat(lastMonthData['2. high']);
    const low = parseFloat(lastMonthData['3. low']);

    const volatility = (high - low) / 20;
    
    let bias = 1.0;
    if (rsi > 70) bias = 0.8;
    if (rsi < 30) bias = 1.2;

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
