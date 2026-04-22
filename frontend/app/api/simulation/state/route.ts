import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const env = req.nextUrl.searchParams.get('env') || 'local';
  try {
    const res = await fetch(`${BACKEND_URL}/simulation/state?env=${encodeURIComponent(env)}`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ simulations: [] }, { status: 200 });
  }
}

export async function POST(req: NextRequest) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const body = await req.json();
    const res = await fetch(`${BACKEND_URL}/simulation/state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ saved: false }, { status: 200 });
  } finally {
    clearTimeout(timeout);
  }
}
