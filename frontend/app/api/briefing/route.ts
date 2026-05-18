import { NextResponse } from 'next/server';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/briefing`, { next: { revalidate: 900 } });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
