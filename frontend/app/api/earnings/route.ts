import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/earnings/calendar`, {
      next: { revalidate: 21600 },
      signal: AbortSignal.timeout(50000), // 50s — backend may take up to 45s on cold cache
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    console.error('[earnings] proxy error:', err);
    return NextResponse.json({ error: 'Failed to load earnings calendar' }, { status: 502 });
  }
}
