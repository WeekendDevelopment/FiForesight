import { NextRequest, NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params;
  try {
    const { data } = await axios.get(`${BACKEND}/orderbook/${symbol}`, { timeout: 10000 });
    return NextResponse.json(data);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status ?? 500;
    const detail =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      'Order book fetch failed';
    return NextResponse.json({ error: detail }, { status });
  }
}
