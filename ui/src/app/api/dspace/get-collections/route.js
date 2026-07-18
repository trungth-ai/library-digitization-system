// File: src/app/api/dspace/get-collections/route.js
import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(req) {
  try {
    const cookie = req.headers.get("cookie");
    const { dspaceUrl } = await req.json();

    if (!dspaceUrl) {
      return NextResponse.json(
        { error: "Missing dspaceUrl" },
        { status: 400 }
      );
    }

    // Fetch all collections from DSpace
    // Use limit=1000 to get all collections in one request
    const res = await fetch(`${dspaceUrl}/rest/collections?limit=1000`, {
      headers: {
        Cookie: cookie || '',
        Accept: "application/json",
      },
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: "Failed to fetch collections", detail: text },
        { status: res.status }
      );
    }

    const text = await res.text();
    const trimmed = text.trim();

    let collections = [];

    if (trimmed.startsWith("[")) {
      // JSON array response
      collections = JSON.parse(text);
    } else if (trimmed.startsWith("{")) {
      // JSON object response (might be paginated)
      const data = JSON.parse(text);
      collections = data.collections || data._embedded?.collections || [data];
    } else {
      return NextResponse.json(
        { error: "Unexpected response format", raw: text.substring(0, 500) },
        { status: 500 }
      );
    }

    // Normalize collection data
    const normalized = collections.map(col => ({
      id: col.id || col.uuid,
      uuid: col.uuid || col.id,
      name: col.name,
      handle: col.handle,
      // Extract metadata if available
      description: col.introductoryText || 
                   col.shortDescription || 
                   col.metadata?.['dc.description']?.[0]?.value || 
                   col.metadata?.['dc.description.abstract']?.[0]?.value ||
                   '',
      type: col.type,
      // Extract useful metadata for AI matching
      subjects: col.metadata?.['dc.subject'] || [],
      archivedItemsCount: col.numberItems || col.archivedItemsCount || 0
    }));

    console.log(`Found ${normalized.length} collections`);

    return NextResponse.json({
      success: true,
      count: normalized.length,
      collections: normalized
    });

  } catch (err) {
    console.error('Get collections error:', err);
    return NextResponse.json(
      { error: "Internal error", message: err.message },
      { status: 500 }
    );
  }
}