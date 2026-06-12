import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// GET /api/portfolio/summary → backend /portfolio/summary (auth required).
// Heavy endpoint (yfinance fan-out) — allow a longer timeout than CRUD.
export async function GET(req: NextRequest) {
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 20_000);
  const auth       = req.headers.get('authorization') ?? '';
  const refresh    = req.nextUrl.searchParams.get('refresh') === 'true';
  const url        = `${BACKEND_URL}/portfolio/summary${refresh ? '?refresh=true' : ''}`;
  try {
    const res  = await fetch(url, {
      headers: auth ? { authorization: auth } : {},
      signal:  controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'Portfolio summary unavailable.' }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
