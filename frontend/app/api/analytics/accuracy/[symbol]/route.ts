import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params;

  // Forward auth + client-IP context so backend rate-limiting/auth see the real
  // caller rather than the Next.js server (matches predict/route.ts).
  const headers: Record<string, string> = {};
  const auth = req.headers.get('authorization');
  if (auth) headers['Authorization'] = auth;
  const fwd = req.headers.get('x-forwarded-for');
  if (fwd) headers['x-forwarded-for'] = fwd;

  try {
    const res = await fetch(`${BACKEND_URL}/analytics/accuracy/${encodeURIComponent(symbol)}`, {
      headers,
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      // Preserve upstream detail (e.g. 422 invalid symbol, 429 rate limit) + status.
      const detail = (data && (data.detail ?? data.error)) ?? 'Accuracy analytics fetch failed';
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: `Accuracy analytics unavailable: ${message}` }, { status: 502 });
  }
}
