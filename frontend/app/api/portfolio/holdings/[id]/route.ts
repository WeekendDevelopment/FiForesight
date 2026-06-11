import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// DELETE /api/portfolio/holdings/{id} → backend /portfolio/holdings/{id} (auth required)
export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const auth   = req.headers.get('authorization') ?? '';
  try {
    const res  = await fetch(`${BACKEND_URL}/portfolio/holdings/${encodeURIComponent(id)}`, {
      method:  'DELETE',
      headers: auth ? { authorization: auth } : {},
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'Could not delete holding.' }, { status: 502 });
  }
}
