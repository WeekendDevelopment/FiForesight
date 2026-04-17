import { NextResponse } from 'next/server';
import axios from 'axios';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const tickers = searchParams.get('tickers') || '';
    const response = await axios.get(`${BACKEND_URL}/sparklines`, { params: { tickers } });
    return NextResponse.json(response.data);
  } catch (error: any) {
    return NextResponse.json({}, { status: error.response?.status || 500 });
  }
}
