import { NextResponse } from 'next/server';
import axios from 'axios';

export async function POST(request: Request) {
  const { data } = await request.json();
  const symbol = (data || 'SPY').toUpperCase();

  try {
    console.log(`Fetching quote for: ${symbol}`);
    
    // Using GLOBAL_QUOTE for real-time price info (usually very stable on free tier)
    const response = await axios.get(`http://localhost:8000/global-quote`, {
      params: {
        symbol: symbol
      }
    });

    const quote = response.data['Global Quote'];

    if (!quote || Object.keys(quote).length === 0) {
      const note = response.data['Note'];
      if (note) {
        return NextResponse.json({ 
          error: 'Alpha Vantage Free Tier Limit Reached (5 calls/min). Please wait 60 seconds.' 
        }, { status: 429 });
      }
      return NextResponse.json({ 
        error: `Could not find data for "${symbol}". Try "SPY" for S&P 500.` 
      }, { status: 400 });
    }

    const currentPrice = parseFloat(quote['05. price']);
    const previousClose = parseFloat(quote['08. previous close']);
    const high = parseFloat(quote['03. high']);
    const low = parseFloat(quote['04. low']);

    // Simplified prediction for 24-48 hours
    const priceChange = currentPrice - previousClose;
    const volatility = (high - low) || (currentPrice * 0.01); // fallback if high/low missing
    
    const predictedHigh = currentPrice + (volatility * 0.5);
    const predictedLow = currentPrice - (volatility * 0.5);

    return NextResponse.json({
      symbol,
      currentPrice: currentPrice.toFixed(2),
      prediction: {
        highRange: predictedHigh.toFixed(2),
        lowRange: predictedLow.toFixed(2),
        trend: priceChange >= 0 ? 'Bullish' : 'Bearish'
      },
      lastUpdated: new Date().toISOString()
    });

  } catch (error: any) {
    console.error('Alpha Vantage Error:', error);
    return NextResponse.json({ error: 'Failed to connect to Alpha Vantage servers.' }, { status: 500 });
  }
}
