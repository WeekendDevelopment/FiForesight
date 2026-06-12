import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// GET /api/alerts/rules → backend /alerts/rules (auth required)
export async function GET(req: NextRequest) {
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 10_000);
  const auth       = req.headers.get('authorization') ?? '';
  try {
    const res  = await fetch(`${BACKEND_URL}/alerts/rules`, {
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

// POST /api/alerts/rules → backend /alerts/rules (auth required)
export async function POST(req: NextRequest) {
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 10_000);
  const auth       = req.headers.get('authorization') ?? '';
  try {
    let body: unknown;
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ detail: 'Invalid JSON body.' }, { status: 400 });
    }
    const res  = await fetch(`${BACKEND_URL}/alerts/rules`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', ...(auth ? { authorization: auth } : {}) },
      body:    JSON.stringify(body),
      signal:  controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'Could not create alert rule.' }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
