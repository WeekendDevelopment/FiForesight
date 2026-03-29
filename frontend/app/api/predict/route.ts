import { NextResponse } from 'next/server';
import axios from 'axios';

// Ensure BACKEND_URL doesn't have a trailing slash for consistency
let BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
if (BACKEND_URL.endsWith('/')) {
  BACKEND_URL = BACKEND_URL.slice(0, -1);
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const symbol = (body.data || 'SPY').toUpperCase();

    console.log(`Proxying prediction request for ${symbol} to ${BACKEND_URL}`);

    // Delegate prediction logic to the Python backend
    const response = await axios.post(`${BACKEND_URL}/predict`, { data: symbol });

    return NextResponse.json(response.data);

  } catch (error: any) {
    console.error('Backend Proxy Error:', error.response?.data || error.message);
    
    const status = error.response?.status || 500;
    const detail = error.response?.data?.detail || 'Failed to communicate with forecasting engine.';
    
    return NextResponse.json({ error: detail }, { status });
  }
}
