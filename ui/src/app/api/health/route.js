import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Health check cho container UI (Dockerfile HEALTHCHECK + docker-compose gọi endpoint này).
export async function GET() {
  return NextResponse.json({ status: "ok", service: "ui" });
}
