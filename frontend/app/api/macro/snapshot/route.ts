import { NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000';

export async function GET() {
  try {
    const { data } = await axios.get(`${BACKEND}/macro/snapshot`, { timeout: 10000 });
    return NextResponse.json(data);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status ?? 500;
    return NextResponse.json({ error: 'Macro snapshot fetch failed' }, { status });
  }
}
