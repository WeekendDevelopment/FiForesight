import { NextResponse } from 'next/server';
import axios from 'axios';

// Since both frontend and backend are in the same container,
// the frontend can talk to the backend via localhost:8000 internally.
// This address is NOT exposed to the public internet.
const INTERNAL_BACKEND_URL = 'http://127.0.0.1:8000';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const symbol = (body.data || 'SPY').toUpperCase();

    console.log(`[Internal Proxy] Routing ${symbol} to ${INTERNAL_BACKEND_URL}/predict`);

    const response = await axios.post(`${INTERNAL_BACKEND_URL}/predict`, { 
      data: symbol 
    }, {
      timeout: 25000, // High timeout for free tier wake-ups
      headers: { 'Content-Type': 'application/json' }
    });

    return NextResponse.json(response.data);

  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message;
    console.error(`[Internal Proxy] Backend Error:`, errorMessage);
    
    return NextResponse.json({ 
      error: `Service error: ${errorMessage}` 
    }, { status: error.response?.status || 500 });
  }
}
