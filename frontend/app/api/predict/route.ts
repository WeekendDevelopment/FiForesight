import { NextResponse } from 'next/server';
import axios from 'axios';

export async function POST(request: Request) {
  // Check both possible names
  const envBackendUrl = process.env.BACKEND_URL;
  const publicBackendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;
  
  const FINAL_URL = envBackendUrl || publicBackendUrl;

  // If this error shows up on the website, the Vercel variables are definitely not reaching the code
  if (!FINAL_URL) {
    console.error('[Proxy] Environment Variable Missing. Deployment needs redeploy.');
    return NextResponse.json({ 
      error: 'Configuration Error: No Backend URL found. Please redeploy this branch in Vercel.' 
    }, { status: 500 });
  }

  const sanitizedUrl = FINAL_URL.endsWith('/') ? FINAL_URL.slice(0, -1) : FINAL_URL;

  try {
    const body = await request.json();
    const symbol = (body.data || 'SPY').toUpperCase();

    console.log(`[Proxy] Target: ${sanitizedUrl}/predict`);

    const response = await axios.post(`${sanitizedUrl}/predict`, { 
      data: symbol 
    }, {
      timeout: 25000,
      headers: { 'Content-Type': 'application/json' }
    });

    return NextResponse.json(response.data);

  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message;
    console.error(`[Proxy] Backend Error:`, errorMessage);
    
    return NextResponse.json({ 
      error: `Backend error: ${errorMessage}`
    }, { status: error.response?.status || 500 });
  }
}
