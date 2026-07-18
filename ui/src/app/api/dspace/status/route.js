// File: src/app/api/dspace/status/route.js
import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(req) {
  const cookie = req.headers.get("cookie");
  const { dspaceUrl } = await req.json();

  const res = await fetch(`${dspaceUrl}/rest/status`, {
    headers: {
      Cookie: cookie,
      Accept: "application/json",
    },
  });

  const text = await res.text();

  // Nếu DSpace vẫn trả XML / HTML → coi như chưa authenticated
  if (!res.headers.get("content-type")?.includes("application/json")) {
    return NextResponse.json({
      authenticated: false,
      raw: text,
    });
  }

  return new NextResponse(text, {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}