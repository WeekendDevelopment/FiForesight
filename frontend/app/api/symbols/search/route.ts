import { NextRequest, NextResponse } from 'next/server';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// Live symbol search for the command palette (F33) → GET /symbols/search?q=
// Returns [] on any failure so the palette degrades to its static universe.
export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get('q')?.trim() ?? '';
  if (!q) return NextResponse.json([]);
  try {
    // no-store: the backend Redis-caches results 6h; caching here would also
    // pin transient-failure [] responses for the revalidate window.
    const res = await fetch(
      `${BACKEND_URL}/symbols/search?q=${encodeURIComponent(q)}`,
      { cache: 'no-store', signal: AbortSignal.timeout(10000) },
    );
    if (!res.ok) return NextResponse.json([]);
    const data = await res.json();
    return NextResponse.json(Array.isArray(data) ? data : []);
  } catch {
    return NextResponse.json([]);
  }
}
