import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 15_000);
  try {
    const { searchParams } = new URL(req.url);
    const symbols = searchParams.get('symbols') ?? '';
    const auth    = req.headers.get('authorization') || '';
    const qs      = new URLSearchParams();
    if (symbols) qs.set('symbols', symbols);
    const res  = await fetch(`${BACKEND_URL}/watchlist/metrics?${qs.toString()}`, {
      headers: auth ? { Authorization: auth } : {},
      signal: controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json([], { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
