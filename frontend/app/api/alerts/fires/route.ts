import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// GET /api/alerts/fires → backend /alerts/fires (auth required)
export async function GET(req: NextRequest) {
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 10_000);
  const auth       = req.headers.get('authorization') ?? '';
  try {
    const res  = await fetch(`${BACKEND_URL}/alerts/fires`, {
      headers: auth ? { authorization: auth } : {},
      signal:  controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'Alerts service unavailable.' }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
