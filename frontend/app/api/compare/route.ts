import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const symbols = req.nextUrl.searchParams.get('symbols') ?? '';
  try {
    const res = await fetch(
      `${BACKEND_URL}/compare?symbols=${encodeURIComponent(symbols)}`,
      { method: 'GET' },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    console.error('Compare proxy error:', err.message);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
