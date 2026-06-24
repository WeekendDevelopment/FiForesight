import { NextResponse } from 'next/server';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/sectors/heatmap`, {
      next: { revalidate: 900 },
      signal: AbortSignal.timeout(25000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    console.error('[sectors/heatmap] proxy error:', err);
    return NextResponse.json({ error: 'Failed to load sector heatmap data' }, { status: 502 });
  }
}
