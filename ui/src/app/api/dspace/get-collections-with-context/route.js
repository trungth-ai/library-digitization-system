// File: src/app/api/dspace/get-collections-with-context/route.js
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

    // ✅ STEP 1: Get all communities first
    const communitiesRes = await fetch(`${dspaceUrl}/rest/communities?limit=1000`, {
      headers: {
        Cookie: cookie || '',
        Accept: "application/json",
      },
    });

    if (!communitiesRes.ok) {
      throw new Error("Failed to fetch communities");
    }

    const communitiesText = await communitiesRes.text();
    let communities = [];
    
    try {
      const trimmed = communitiesText.trim();
      if (trimmed.startsWith("[")) {
        communities = JSON.parse(communitiesText);
      } else if (trimmed.startsWith("{")) {
        const data = JSON.parse(communitiesText);
        communities = data.communities || data._embedded?.communities || [data];
      }
    } catch (e) {
      console.error("Failed to parse communities:", e);
    }

    console.log(`Found ${communities.length} communities`);

    // ✅ STEP 2: For each community, get its collections
    const collectionsWithContext = [];

    for (const community of communities) {
      const communityId = community.id || community.uuid;
      const communityName = community.name;
      
      try {
        // Get collections in this community
        const colRes = await fetch(
          `${dspaceUrl}/rest/communities/${communityId}/collections`,
          {
            headers: {
              Cookie: cookie || '',
              Accept: "application/json",
            },
          }
        );

        if (!colRes.ok) {
          console.warn(`Failed to get collections for community ${communityId}`);
          continue;
        }

        const colText = await colRes.text();
        let collections = [];

        try {
          const trimmed = colText.trim();
          if (trimmed.startsWith("[")) {
            collections = JSON.parse(colText);
          } else if (trimmed.startsWith("{")) {
            const data = JSON.parse(colText);
            collections = data.collections || data._embedded?.collections || [data];
          }
        } catch (e) {
          console.error(`Failed to parse collections for community ${communityId}:`, e);
          continue;
        }

        // Add community context to each collection
        for (const col of collections) {
          collectionsWithContext.push({
            id: col.id || col.uuid,
            uuid: col.uuid || col.id,
            name: col.name,
            handle: col.handle,
            description: col.introductoryText || 
                         col.shortDescription || 
                         col.metadata?.['dc.description']?.[0]?.value || 
                         col.metadata?.['dc.description.abstract']?.[0]?.value ||
                         '',
            type: col.type,
            
            // ✅ ADD COMMUNITY CONTEXT
            communityId: communityId,
            communityName: communityName,
            communityHandle: community.handle,
            
            // Display name with context
            displayName: `${col.name} (${communityName})`,
            
            // For AI matching
            fullContext: `${communityName} > ${col.name}`,
            
            // Extract metadata
            subjects: col.metadata?.['dc.subject'] || [],
            archivedItemsCount: col.numberItems || col.archivedItemsCount || 0
          });
        }

      } catch (err) {
        console.error(`Error processing community ${communityId}:`, err);
      }
    }

    console.log(`Found ${collectionsWithContext.length} collections with context`);

    return NextResponse.json({
      success: true,
      count: collectionsWithContext.length,
      collections: collectionsWithContext
    });

  } catch (err) {
    console.error('Get collections with context error:', err);
    return NextResponse.json(
      { error: "Internal error", message: err.message },
      { status: 500 }
    );
  }
}