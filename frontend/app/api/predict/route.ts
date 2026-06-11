import { NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const symbol = (body.data || 'SPY').toUpperCase();
    const auth = request.headers.get('authorization') || '';

    const response = await axios.post(
      `${BACKEND_URL}/predict`,
      { data: symbol },
      auth ? { headers: { Authorization: auth } } : undefined,
    );

    return NextResponse.json(response.data);

  } catch (error: any) {
    console.error('Backend Proxy Error:', error.response?.data || error.message);

    const status = error.response?.status || 500;
    const detail = error.response?.data?.detail || 'Internal server error';

    return NextResponse.json({ error: detail }, { status });
  }
}
