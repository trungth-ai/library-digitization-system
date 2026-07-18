import { NextResponse } from 'next/server';

export async function DELETE(req, { params }) {
  try {
    const { jobId } = await params;
    const ocrApiUrl = process.env.NEXT_PUBLIC_OCR_API_URL;

    console.log(`Deleting job: ${jobId}`);

    const res = await fetch(`${ocrApiUrl}/api/v2/jobs/${jobId}`, {
      method: 'DELETE',
    });

    if (!res.ok) {
      const errorText = await res.text();
      console.error('FastAPI delete error:', errorText);
      return NextResponse.json(
        { error: 'Failed to delete job', detail: errorText },
        { status: res.status }
      );
    }

    const data = await res.json();
    console.log(`Job ${jobId} deleted successfully`);

    return NextResponse.json(data);

  } catch (err) {
    console.error('Delete job error:', err);
    return NextResponse.json(
      { error: 'Failed to delete job', message: err.message },
      { status: 500 }
    );
  }
}