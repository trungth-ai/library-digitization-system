// File: src/app/api/dspace/get-item-by-handle/route.js
import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(req) {
  try {
    const cookie = req.headers.get("cookie");
    const { handle, dspaceUrl } = await req.json();

    if (!handle || !dspaceUrl) {
      return NextResponse.json(
        { error: "Missing handle or dspaceUrl" },
        { status: 400 }
      );
    }

    // DSpace REST API: GET /handle/{prefix}/{suffix}
    // Example: /handle/123456789/12345
    const handleUrl = `${dspaceUrl}/rest/handle/${handle}`;
    console.log('Fetching item by handle:', handleUrl);

    const res = await fetch(handleUrl, {
      headers: {
        Cookie: cookie,
        Accept: "application/json",
      },
    });

    const text = await res.text();

    if (!res.ok) {
      console.error('Failed to get item by handle:', text);
      return NextResponse.json(
        { error: "Failed to get item by handle", detail: text },
        { status: res.status }
      );
    }

    // Parse response
    const trimmed = text.trim();
    let itemData;

    if (trimmed.startsWith("{")) {
      itemData = JSON.parse(text);
    } else if (trimmed.startsWith("<")) {
      // Parse XML if needed
      const idMatch = text.match(/<id>(\d+)<\/id>/);
      const handleMatch = text.match(/<handle>([^<]+)<\/handle>/);
      itemData = {
        id: idMatch ? parseInt(idMatch[1]) : null,
        handle: handleMatch ? handleMatch[1] : null,
      };
    } else {
      return NextResponse.json(
        { error: "Unknown response format", raw: text },
        { status: 500 }
      );
    }

    if (!itemData.id) {
      return NextResponse.json(
        { error: "Item ID not found in response", data: itemData },
        { status: 500 }
      );
    }

    console.log('Got item ID:', itemData.id);

    return NextResponse.json({
      success: true,
      id: itemData.id,
      handle: itemData.handle,
      type: itemData.type,
    });

  } catch (err) {
    console.error('Get item by handle error:', err);
    return NextResponse.json(
      { error: "Internal error", message: err.message },
      { status: 500 }
    );
  }
}