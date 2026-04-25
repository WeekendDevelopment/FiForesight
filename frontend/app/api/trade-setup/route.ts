import { NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const response = await axios.post(`${BACKEND_URL}/trade-setup`, body);
    return NextResponse.json(response.data);
  } catch (error: any) {
    const status = error.response?.status || 500;
    const detail = error.response?.data?.detail || 'Trade setup failed';
    return NextResponse.json({ error: detail }, { status });
  }
}
