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

    // Re-run the analyst jury with live tools forced on (Groq function calling).
    // Longer client timeout: forced tool round-trips take longer than a normal call.
    const response = await axios.post(
      `${BACKEND_URL}/jury/reanalyze`,
      { symbol },
      { timeout: 45000 },
    );

    return NextResponse.json(response.data);

  } catch (error: any) {
    console.error('Jury Reanalyze Proxy Error:', error.response?.data || error.message);

    const status = error.response?.status || 500;
    const detail = error.response?.data?.detail || 'Re-analysis failed';

    return NextResponse.json({ error: detail }, { status });
  }
}
