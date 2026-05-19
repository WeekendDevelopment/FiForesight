import { NextResponse } from 'next/server';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/sectors`, {
      next: { revalidate: 900 },
      signal: AbortSignal.timeout(8000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    console.error('[sectors] proxy error:', err);
    return NextResponse.json({ error: 'Failed to load sector data' }, { status: 502 });
  }
}
