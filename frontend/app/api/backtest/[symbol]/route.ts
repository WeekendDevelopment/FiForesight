import { NextRequest, NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params;
  try {
    // Backtest fits 3 models per rolling window (~30s); allow more than the
    // backend's 120s budget so the proxy doesn't time out first.
    const { data } = await axios.get(`${BACKEND}/backtest/${symbol}`, { timeout: 125000 });
    return NextResponse.json(data);
  } catch (err: unknown) {
    const resp = (err as { response?: { status?: number; data?: { detail?: string } } })?.response;
    const status = resp?.status ?? 500;
    const detail = resp?.data?.detail ?? 'Backtest fetch failed';
    return NextResponse.json({ error: detail }, { status });
  }
}
