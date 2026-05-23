import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol   = searchParams.get('symbol')   || '';
  const period   = searchParams.get('period')   || '2y';
  const interval = searchParams.get('interval') || '1d';

  if (!symbol) {
    return NextResponse.json({ error: 'symbol is required' }, { status: 400 });
  }

  try {
    const url = `${BACKEND_URL}/history?symbol=${encodeURIComponent(symbol)}&period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(30_000) });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    console.error('[history] proxy error:', err);
    return NextResponse.json({ error: 'Failed to fetch history' }, { status: 502 });
  }
}
