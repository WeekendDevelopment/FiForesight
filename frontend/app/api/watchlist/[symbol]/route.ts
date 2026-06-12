import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// DELETE /api/watchlist/[symbol] → backend DELETE /watchlist/{symbol}
export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const controller = new AbortController();
  const timeout    = setTimeout(() => controller.abort(), 15_000);
  const auth       = req.headers.get('authorization') ?? '';
  const { symbol } = await params;
  try {
    const res = await fetch(`${BACKEND_URL}/watchlist/${encodeURIComponent(symbol)}`, {
      method:  'DELETE',
      headers: auth ? { authorization: auth } : {},
      signal:  controller.signal,
    });
    if (res.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'Could not remove from watchlist.' }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
