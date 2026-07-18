// File: src/app/api/dspace/upload-bitstream/route.js
import { NextResponse } from "next/server";

export const runtime = "nodejs";

function parseXMLBitstreamResponse(xmlText) {
  try {
    const idMatch = xmlText.match(/<id>(\d+)<\/id>/);
    const nameMatch = xmlText.match(/<n>([^<]+)<\/name>/);
    const sizeMatch = xmlText.match(/<sizeBytes>(\d+)<\/sizeBytes>/);

    return {
      id: idMatch ? parseInt(idMatch[1]) : null,
      name: nameMatch ? nameMatch[1] : null,
      sizeBytes: sizeMatch ? parseInt(sizeMatch[1]) : null,
    };
  } catch (err) {
    return null;
  }
}

export async function POST(req) {
  try {
    console.log('=== BITSTREAM UPLOAD START ===');
    
    const cookie = req.headers.get("cookie");
    if (!cookie) {
      return NextResponse.json({ error: "No session cookie" }, { status: 401 });
    }

    // Lấy params từ URL
    const url = new URL(req.url);
    const itemId = url.searchParams.get('itemId');
    const fileName = url.searchParams.get('fileName');
    const dspaceUrl = url.searchParams.get('dspaceUrl');

    console.log('Params:', { itemId, fileName, dspaceUrl });

    if (!itemId || !fileName || !dspaceUrl) {
      return NextResponse.json({ error: "Missing params" }, { status: 400 });
    }

    if (itemId === 'undefined' || itemId === 'null') {
      return NextResponse.json({ error: "Invalid itemId" }, { status: 400 });
    }

    // ĐỌC RAW BINARY - KHÔNG PHẢI FORMDATA
    const arrayBuffer = await req.arrayBuffer();
    const fileBuffer = Buffer.from(arrayBuffer);

    console.log('File size:', fileBuffer.length);

    if (fileBuffer.length === 0) {
      return NextResponse.json({ error: "Empty file" }, { status: 400 });
    }

    // URL encode filename
    const encodedFileName = encodeURIComponent(fileName);
    const uploadUrl = `${dspaceUrl}/rest/items/${itemId}/bitstreams?name=${encodedFileName}`;
    
    console.log('Upload URL:', uploadUrl);

    // POST đến DSpace
    const res = await fetch(uploadUrl, {
      method: "POST",
      headers: {
        Cookie: cookie,
        Accept: "application/json",
      },
      body: fileBuffer,
    });

    console.log('DSpace response:', res.status);

    const text = await res.text();

    if (!res.ok) {
      console.error('DSpace error:', text.substring(0, 500));
      return NextResponse.json({
        error: "DSpace upload failed",
        status: res.status,
        detail: text.substring(0, 500),
      }, { status: res.status });
    }

    // Parse response
    const trimmed = text.trim();
    let data;
    
    if (trimmed.startsWith("<")) {
      data = parseXMLBitstreamResponse(text);
    } else if (trimmed.startsWith("{")) {
      data = JSON.parse(text);
    } else {
      data = { message: "Success" };
    }

    console.log('Upload success!');
    return NextResponse.json({
      success: true,
      ...data
    });

  } catch (err) {
    console.error('Upload error:', err);
    return NextResponse.json({
      error: "Internal error",
      message: err.message
    }, { status: 500 });
  }
}