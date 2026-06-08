import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET(request: Request) {
  // `?refresh=1` forces a live re-fetch, bypassing both the Next.js fetch cache
  // and the backend Redis cache (useful for ops / verifying the data source).
  const refresh = new URL(request.url).searchParams.has('refresh');
  try {
    const res = await fetch(`${BACKEND_URL}/ipo/calendar${refresh ? '?refresh=true' : ''}`, {
      ...(refresh
        ? { cache: 'no-store' }
        : { next: { revalidate: 14400 } }), // 4h — matches backend Redis TTL
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    console.error('[ipo] proxy error:', err);
    return NextResponse.json({ error: 'Failed to load IPO calendar' }, { status: 502 });
  }
}
