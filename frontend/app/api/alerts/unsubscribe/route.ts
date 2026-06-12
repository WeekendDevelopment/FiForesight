import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// POST /api/alerts/unsubscribe → backend /alerts/unsubscribe (auth required)
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
    const res  = await fetch(`${BACKEND_URL}/alerts/unsubscribe`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', ...(auth ? { authorization: auth } : {}) },
      body:    JSON.stringify(body),
      signal:  controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'Could not remove push subscription.' }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
