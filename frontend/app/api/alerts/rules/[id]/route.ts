import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// PATCH /api/alerts/rules/{id} → backend /alerts/rules/{id} (auth required)
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const auth   = req.headers.get('authorization') ?? '';
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 10_000);
  try {
    let body: unknown;
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ detail: 'Invalid JSON body.' }, { status: 400 });
    }
    const res  = await fetch(`${BACKEND_URL}/alerts/rules/${encodeURIComponent(id)}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json', ...(auth ? { authorization: auth } : {}) },
      body:    JSON.stringify(body),
      signal:  controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'Could not update alert rule.' }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}

// DELETE /api/alerts/rules/{id} → backend /alerts/rules/{id} (auth required)
export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const auth   = req.headers.get('authorization') ?? '';
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 10_000);
  try {
    const res  = await fetch(`${BACKEND_URL}/alerts/rules/${encodeURIComponent(id)}`, {
      method:  'DELETE',
      headers: auth ? { authorization: auth } : {},
      signal:  controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'Could not delete alert rule.' }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
