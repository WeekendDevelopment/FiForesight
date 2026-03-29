import { NextResponse } from 'next/server';
import axios from 'axios';

// Check both possible environment variable names for maximum compatibility
let BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

if (BACKEND_URL.endsWith('/')) {
  BACKEND_URL = BACKEND_URL.slice(0, -1);
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const symbol = (body.data || 'SPY').toUpperCase();

    // This will show up in your Vercel Runtime Logs
    console.log(`[Proxy] Target: ${BACKEND_URL}, Symbol: ${symbol}`);

    if (BACKEND_URL.includes('127.0.0.1') || BACKEND_URL.includes('localhost')) {
      console.warn('[Proxy] WARNING: BACKEND_URL is still pointing to localhost. Ensure environment variables are set in Vercel.');
    }

    // Delegate prediction logic to the Python backend
    const response = await axios.post(`${BACKEND_URL}/predict`, { data: symbol });

    return NextResponse.json(response.data);

  } catch (error: any) {
    // Log the full error for debugging in Vercel
    console.error('[Proxy] Error:', error.message);
    if (error.response) {
      console.error('[Proxy] Backend Response Data:', error.response.data);
    }
    
    const status = error.response?.status || 500;
    const detail = error.response?.data?.detail || 'Failed to communicate with forecasting engine.';
    
    return NextResponse.json({ error: detail }, { status });
  }
}
