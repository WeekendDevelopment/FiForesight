import { NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const auth = request.headers.get('authorization') || '';

    const response = await axios.post(
      `${BACKEND_URL}/day-trade-setup`,
      body,
      { headers: { ...(auth ? { Authorization: auth } : {}) } },
    );
    return NextResponse.json(response.data);
  } catch (error: any) {
    const status = error.response?.status || 500;
    const detail = error.response?.data?.detail || 'Day-trade setup failed';
    return NextResponse.json({ error: detail }, { status });
  }
}
