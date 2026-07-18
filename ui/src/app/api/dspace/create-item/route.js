// File: src/app/api/dspace/create-item/route.js
import { NextResponse } from "next/server";

export const runtime = "nodejs";

// Helper to parse XML response from DSpace
function parseXMLItemResponse(xmlText) {
  try {
    // Extract key fields from XML using regex (simple parser for DSpace XML)
    const idMatch = xmlText.match(/<id>(\d+)<\/id>/);
    const uuidMatch = xmlText.match(/<uuid>([a-f0-9-]+)<\/uuid>/);
    const handleMatch = xmlText.match(/<handle>([^<]+)<\/handle>/);
    const nameMatch = xmlText.match(/<name>([^<]+)<\/name>/);
    const archivedMatch = xmlText.match(/<archived>([^<]+)<\/archived>/);
    // Extract UUID from link like /rest/items/335530b9-ed0e-4616-b81b-25cd3f14f9e9
    const linkMatch = xmlText.match(/<link>\/rest\/items\/([a-f0-9-]+)<\/link>/);

    // DSpace 6.3 uses UUID as primary identifier
    const itemUuid = uuidMatch ? uuidMatch[1] : (linkMatch ? linkMatch[1] : null);
    const itemId = idMatch ? parseInt(idMatch[1]) : null;

    return {
      id: itemId,
      uuid: itemUuid,
      // Use UUID as primary ID if available, fallback to numeric ID
      itemId: itemUuid || itemId,
      handle: handleMatch ? handleMatch[1] : null,
      name: nameMatch ? nameMatch[1] : null,
      archived: archivedMatch ? archivedMatch[1] : "false",
      type: "item",
      _rawXML: xmlText,
    };
  } catch (err) {
    console.error("XML parsing error:", err);
    return null;
  }
}

export async function POST(req) {
  try {
    const cookie = req.headers.get("cookie");
    
    if (!cookie) {
      return NextResponse.json(
        { error: "No session cookie - please login first" },
        { status: 401 }
      );
    }

    const { collectionId, metadata, dspaceUrl } = await req.json();

    if (!collectionId || !metadata || !dspaceUrl) {
      return NextResponse.json(
        { error: "Missing required fields: collectionId, metadata, dspaceUrl" },
        { status: 400 }
      );
    }

    // Validate metadata format
    if (!Array.isArray(metadata)) {
      return NextResponse.json(
        { error: "metadata must be an array" },
        { status: 400 }
      );
    }

    // Build payload exactly as DSpace 6.3 expects
    const payload = {
      metadata: metadata.map(m => ({
        key: m.key,
        value: m.value,
        language: m.language || null
      }))
    };

    console.log('Creating item with metadata:', JSON.stringify(payload, null, 2));

    // POST to DSpace create item endpoint
    const res = await fetch(
      `${dspaceUrl}/rest/collections/${collectionId}/items`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Cookie: cookie,
          Accept: "application/json",
          "User-Agent": "PostmanRuntime/7.x",
        },
        body: JSON.stringify(payload),
      }
    );

    // Always read as text first (DSpace may return XML)
    const responseText = await res.text();
    console.log('Create item response:', responseText.substring(0, 500));

    if (!res.ok) {
      return NextResponse.json(
        {
          error: "Failed to create item",
          status: res.status,
          detail: responseText,
        },
        { status: res.status }
      );
    }

    // Try to detect response format
    const trimmed = responseText.trim();
    let itemData;

    if (trimmed.startsWith("<")) {
      // XML response - parse it
      console.log("DSpace returned XML response");
      itemData = parseXMLItemResponse(responseText);
      
      if (!itemData) {
        return NextResponse.json(
          {
            error: "Failed to parse XML response",
            raw: responseText.substring(0, 1000),
          },
          { status: 500 }
        );
      }
    } else if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      // JSON response
      try {
        itemData = JSON.parse(responseText);
        
        // Extract UUID from link field if present
        // Example: "link": "/rest/items/335530b9-ed0e-4616-b81b-25cd3f14f9e9"
        let itemUuid = null;
        if (itemData.link) {
          const uuidMatch = itemData.link.match(/\/items\/([a-f0-9-]+)/);
          if (uuidMatch) {
            itemUuid = uuidMatch[1];
          }
        }
        
        // Use UUID as primary identifier, fallback to id
        itemData.itemId = itemUuid || itemData.uuid || itemData.id;
        itemData.uuid = itemUuid || itemData.uuid;
        
      } catch (err) {
        return NextResponse.json(
          {
            error: "Failed to parse JSON response",
            raw: responseText,
          },
          { status: 500 }
        );
      }
    } else {
      // Unknown format
      return NextResponse.json(
        {
          error: "Unknown response format",
          raw: responseText,
        },
        { status: 500 }
      );
    }

    console.log('Parsed item data:', {
      itemId: itemData.itemId,
      id: itemData.id,
      uuid: itemData.uuid,
      handle: itemData.handle
    });

    // ⚠️ Nếu không có itemId/uuid, cần gọi GET item by handle
    if (!itemData.itemId && itemData.handle) {
      console.log('No itemId in response, fetching by handle:', itemData.handle);
      
      try {
        const handleUrl = `${dspaceUrl}/rest/handle/${itemData.handle}`;
        const handleRes = await fetch(handleUrl, {
          headers: {
            Cookie: cookie,
            Accept: "application/json",
          },
        });

        if (handleRes.ok) {
          const handleText = await handleRes.text();
          const handleTrimmed = handleText.trim();
          
          if (handleTrimmed.startsWith("{")) {
            const handleData = JSON.parse(handleText);
            itemData.itemId = handleData.uuid || handleData.id;
            itemData.id = handleData.id;
            itemData.uuid = handleData.uuid;
            console.log('Got itemId from handle lookup:', itemData.itemId);
          }
        }
      } catch (err) {
        console.error('Failed to lookup item by handle:', err);
      }
    }

    // Return normalized item data
    return NextResponse.json({
      success: true,
      itemId: itemData.itemId || null,  // Main ID to use for bitstream upload
      id: itemData.id || null,          // Numeric ID (may be null)
      uuid: itemData.uuid || null,      // UUID (preferred for DSpace 6.3)
      handle: itemData.handle || null,
      name: itemData.name || null,
      archived: itemData.archived || "false",
      message: "Item created successfully",
      _format: trimmed.startsWith("<") ? "xml" : "json",
      _needsHandleLookup: !itemData.itemId && !!itemData.handle, // Flag for client
    });

  } catch (err) {
    console.error("Create item error:", err);
    return NextResponse.json(
      { error: "Internal error", message: err.message },
      { status: 500 }
    );
  }
}