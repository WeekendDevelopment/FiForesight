import { NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const symbol = typeof body?.symbol === 'string'
      ? body.symbol.trim().toUpperCase()
      : '';

    if (!symbol) {
      return NextResponse.json({ error: 'symbol is required' }, { status: 400 });
    }

    const auth = request.headers.get('authorization') || '';
    // useTools=true → forced Groq function calling; false → plain single
    // completion per analyst (cheapest run). Defaults to true for old callers.
    const useTools = body?.useTools !== false;

    // Run the analyst jury on demand (optionally with live tools forced on).
    // Longer client timeout: forced tool round-trips take longer than a normal call.
    const response = await axios.post(
      `${BACKEND_URL}/jury/reanalyze`,
      { symbol, use_tools: useTools },
      {
        timeout: 45000,
        headers: { ...(auth ? { Authorization: auth } : {}) },
      },
    );

    return NextResponse.json(response.data);

  } catch (error: any) {
    console.error('Jury Reanalyze Proxy Error:', error.response?.data || error.message);

    const status = error.response?.status || 500;
    const detail = error.response?.data?.detail || 'Re-analysis failed';

    return NextResponse.json({ error: detail }, { status });
  }
}
