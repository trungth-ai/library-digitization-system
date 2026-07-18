// File: src/app/api/dspace/login/route.js
import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(req) {
  try {
    const { email, password, dspaceUrl } = await req.json();

    // Build form-urlencoded body as per DSpace 6.3 REST API spec
    const body = new URLSearchParams();
    body.append("email", email);
    body.append("password", password);

    // POST to DSpace login endpoint
    const res = await fetch(`${dspaceUrl}/rest/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: "Login failed", detail: text },
        { status: res.status }
      );
    }

    const rawCookie = res.headers.get("set-cookie");

    if (!rawCookie) {
      return NextResponse.json(
        { error: "DSpace did not return session cookie" },
        { status: 500 }
      );
    }

    // 👉 CẮT CHỈ LẤY JSESSIONID
    const jsession = rawCookie.split(";")[0];

    const response = NextResponse.json({
      success: true,
      message: "Login success",
    });

    // 👉 SET COOKIE LẠI CHO BROWSER
    response.headers.set(
      "Set-Cookie",
      `${jsession}; Path=/; HttpOnly; SameSite=Lax`
    );

    return response;
  } catch (err) {
    return NextResponse.json(
      { error: "Internal error", message: err.message },
      { status: 500 }
    );
  }
}