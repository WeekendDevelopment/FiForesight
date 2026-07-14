import { NextRequest, NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000';

// Mirror the backend `_SYMBOL_RE` so a decoded path param can't traverse outside
// the intended /report-card/{symbol} endpoint before reaching the backend's own check.
const SYMBOL_RE = /^[A-Za-z0-9.\-:]{1,15}$/;

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params;
  if (!SYMBOL_RE.test(symbol)) {
    return NextResponse.json({ error: 'Invalid symbol' }, { status: 422 });
  }
  try {
    const authHeader = req.headers.get('authorization');
    const { data } = await axios.get(
      `${BACKEND}/report-card/${encodeURIComponent(symbol)}`,
      {
        timeout: 15000,
        headers: authHeader ? { Authorization: authHeader } : undefined,
      },
    );
    return NextResponse.json(data);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status ?? 500;
    return NextResponse.json({ error: 'Report card fetch failed' }, { status });
  }
}
