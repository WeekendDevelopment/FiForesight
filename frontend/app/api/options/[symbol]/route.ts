import { NextRequest, NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params;
  const expiry = new URL(_req.url).searchParams.get('expiry') ?? '';
  const url = `${BACKEND}/options/${symbol}${expiry ? `?expiry=${encodeURIComponent(expiry)}` : ''}`;
  try {
    const { data } = await axios.get(url, { timeout: 10000 });
    return NextResponse.json(data);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status ?? 500;
    return NextResponse.json({ error: 'Options fetch failed' }, { status });
  }
}
