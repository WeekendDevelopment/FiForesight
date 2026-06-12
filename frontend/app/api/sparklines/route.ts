import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 15_000);
  try {
    const { searchParams } = new URL(req.url);
    const tickers = searchParams.get('tickers') ?? '';
    const extra   = searchParams.get('extra')   ?? '';
    const qs      = new URLSearchParams();
    if (tickers) qs.set('tickers', tickers);
    if (extra)   qs.set('extra',   extra);
    const res  = await fetch(`${BACKEND_URL}/sparklines?${qs.toString()}`, { signal: controller.signal });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json([], { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
