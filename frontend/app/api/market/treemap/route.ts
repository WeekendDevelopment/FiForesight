import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get('authorization') || '';
    const res = await fetch(`${BACKEND_URL}/market/treemap`, {
      headers: auth ? { Authorization: auth } : {},
      next: { revalidate: 600 },
      signal: AbortSignal.timeout(25000),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const detail = (data && (data.detail || data.error)) || 'Failed to load market treemap data';
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    console.error('[market/treemap] proxy error:', err);
    return NextResponse.json({ error: 'Failed to load market treemap data' }, { status: 502 });
  }
}
