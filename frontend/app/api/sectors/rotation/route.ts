import { NextResponse } from 'next/server';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/sectors/rotation`, {
      // Backend already Redis-caches this 1h; keep the proxy window short so the
      // backend TTL stays the freshness boundary (page also re-fetches every 5 min).
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(25000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    console.error('[sectors/rotation] proxy error:', err);
    return NextResponse.json({ error: 'Failed to load sector rotation data' }, { status: 502 });
  }
}
