// File: src/app/api/ai/suggest-collection-batch/route.js

import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(req) {
  try {
    const { documents, collections } = await req.json();

    if (!documents || !Array.isArray(documents) || !collections) {
      return NextResponse.json(
        { error: "Missing required fields or invalid format" },
        { status: 400 },
      );
    }

    const apiKey = process.env.CLAUDE_API_KEY;

    if (!apiKey) {
      return NextResponse.json(
        { error: "CLAUDE_API_KEY not configured in server environment" },
        { status: 500 },
      );
    }

    // ✅ FIXED: Build collections list WITH COMMUNITY CONTEXT
    const collectionsStr = collections
      .map(
        (c, idx) =>
          `${idx + 1}. ID: ${c.id || c.uuid}
   Name: ${c.name}
   Community: ${c.communityName || "N/A"}
   Full Context: ${c.fullContext || c.displayName || c.name}
   Description: ${c.description || "N/A"}
   Handle: ${c.handle || "N/A"}
   Items Count: ${c.archivedItemsCount || 0}`,
      )
      .join("\n\n");

    // Build documents list with metadata
    const documentsStr = documents
      .map((doc, idx) => {
        const metadataStr = doc.metadata
          .map((m) => `  ${m.key}: ${m.value}`)
          .join("\n");
        return `DOCUMENT ${idx + 1}:
Folder: ${doc.folderName}
Title: ${doc.title}
Metadata:
${metadataStr}`;
      })
      .join("\n\n" + "=".repeat(80) + "\n\n");

    // ✅ ENHANCED PROMPT with community context awareness
    const prompt = `You are a library cataloging expert. You need to analyze MULTIPLE documents and suggest the most appropriate DSpace collection for EACH document.

IMPORTANT: Collections with the SAME NAME may exist in DIFFERENT COMMUNITIES. Pay close attention to the "Community" and "Full Context" fields to distinguish them.

AVAILABLE COLLECTIONS:
${collectionsStr}

DOCUMENTS TO ANALYZE:
${"=".repeat(80)}
${documentsStr}

TASK:
For EACH document (1 to ${documents.length}):
1. Analyze the document's metadata (title, author, subject, type, department, abstract, etc.)
2. Match it with the most appropriate collection
3. CRITICAL: Pay special attention to:
   - Document type (Khóa luận, Đồ án, Giáo trình, etc.)
   - Department/Faculty mentioned in metadata (CNTT, Du lịch, XD, Môi trường, etc.)
   - Community context of each collection
4. If multiple collections have the same name, choose based on community match
5. Provide confidence score (0-100)
6. Give brief reasoning (max 2 sentences)

EXAMPLE MATCHING LOGIC:
- If document mentions "Khoa CNTT" or "Công nghệ thông tin" → Choose collection in "Khoa Công nghệ thông tin" community
- If document is "Khóa luận" type → Choose "Khóa luận tốt nghiệp" collection in matching department community
- If document is "Giáo trình" in "Du lịch" field → Choose "Giáo trình" in "Khoa Du lịch" community, NOT in "Khoa CNTT"

RESPOND ONLY WITH THIS JSON FORMAT (no markdown, no explanation):
{
  "suggestions": [
    {
      "documentIndex": 0,
      "folderName": "folder_name_here",
      "collectionId": "the collection ID",
      "collectionName": "the collection name",
      "communityName": "the community name",
      "confidence": 85,
      "reasoning": "Brief explanation mentioning community match"
    }
  ]
}

CRITICAL: Return suggestions array with EXACTLY ${documents.length} items, one for each document.
Return ONLY valid JSON, no markdown blocks, no additional text.`;

    console.log(
      `Analyzing ${documents.length} documents with community context in single API call...`,
    );

    // Call Claude API
    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 4096,
        messages: [
          {
            role: "user",
            content: prompt,
          },
        ],
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error("Claude API error:", error);
      return NextResponse.json(
        { error: "AI service error", detail: error },
        { status: response.status },
      );
    }

    const data = await response.json();
    const aiResponse = data.content[0].text;

    // Parse AI response
    let result;
    try {
      const cleaned = aiResponse
        .replace(/```json\n?/g, "")
        .replace(/```\n?/g, "")
        .trim();
      result = JSON.parse(cleaned);
    } catch (err) {
      console.error("Failed to parse AI response:", aiResponse);
      return NextResponse.json(
        {
          error: "Failed to parse AI response",
          raw: aiResponse.substring(0, 1000),
        },
        { status: 500 },
      );
    }

    // Validate response
    if (!result.suggestions || !Array.isArray(result.suggestions)) {
      return NextResponse.json(
        { error: "AI did not provide suggestions array", raw: result },
        { status: 500 },
      );
    }

    if (result.suggestions.length !== documents.length) {
      console.warn(
        `Expected ${documents.length} suggestions, got ${result.suggestions.length}`,
      );
    }

    console.log(`Successfully analyzed ${result.suggestions.length} documents with community context`);

    return NextResponse.json({
      success: true,
      count: result.suggestions.length,
      suggestions: result.suggestions,
    });
  } catch (err) {
    console.error("Batch suggest collection error:", err);
    return NextResponse.json(
      { error: "Internal error", message: err.message },
      { status: 500 },
    );
  }
}