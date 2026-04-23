import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const env = req.nextUrl.searchParams.get('env') || 'local';
  try {
    const res = await fetch(
      `${BACKEND_URL}/simulation/state/${encodeURIComponent(id)}?env=${encodeURIComponent(env)}`,
      { method: 'DELETE' },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ deleted: false }, { status: 200 });
  }
}
