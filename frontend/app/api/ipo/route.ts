import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/ipo/calendar`, {
      next: { revalidate: 14400 }, // 4h — matches backend Redis TTL
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    console.error('[ipo] proxy error:', err);
    return NextResponse.json({ error: 'Failed to load IPO calendar' }, { status: 502 });
  }
}
