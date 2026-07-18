import { headers } from "next/headers";
import LoginForm from "@/components/LoginForm";
import Header from "@/components/Header";
import PageClient from "./page-client";

const DSPACE_URL = process.env.NEXT_PUBLIC_DSPACE_URL;
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";

/**
 * Check DSpace session server-side
 */
async function getSession() {
  const headersList = await headers();
  const cookie = headersList.get("cookie");

  if (!cookie) {
    console.log("[SSR] No cookie found");
    return null;
  }

  try {
    const res = await fetch(`${SITE_URL}/api/dspace/status`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: cookie,
      },
      body: JSON.stringify({ dspaceUrl: DSPACE_URL }),
      cache: "no-store", // Always fresh
    });

    if (!res.ok) {
      console.log("[SSR] Status check failed:", res.status);
      return null;
    }

    const data = await res.json();
    
    if (data.authenticated) {
      console.log("[SSR] User authenticated:", data.fullname);
      return data;
    }

    return null;
  } catch (err) {
    console.error("[SSR] Session check error:", err);
    return null;
  }
}

/**
 * Fetch collections with community context server-side
 */
async function getCollections(cookie) {
  try {
    console.log("[SSR] Fetching collections...");
    
    const res = await fetch(`${SITE_URL}/api/dspace/get-collections-with-context`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: cookie || "",
      },
      body: JSON.stringify({ dspaceUrl: DSPACE_URL }),
      cache: "no-store", // Always fresh
    });

    if (!res.ok) {
      console.error("[SSR] Collections fetch failed:", res.status);
      return [];
    }

    const data = await res.json();
    
    if (data.success && data.collections) {
      console.log(
        `[SSR] Loaded ${data.collections.length} collections from ` +
        `${new Set(data.collections.map(c => c.communityName)).size} communities`
      );
      return data.collections;
    }

    return [];
  } catch (err) {
    console.error("[SSR] Collections fetch error:", err);
    return [];
  }
}

/**
 * Main page - Server Component (SSR)
 */
export default async function Page() {
  // Server-side data fetching
  const session = await getSession();
  
  const headersList = await headers();
  const cookie = headersList.get("cookie");
  
  // Only fetch collections if user is authenticated
  const collections = session ? await getCollections(cookie) : [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50">
      <Header session={session} />

      <div className="max-w-450 mx-auto p-8">
        {!session?.authenticated ? (
          <div className="max-w-xl mx-auto">
            <LoginForm dspaceUrl={DSPACE_URL} />
          </div>
        ) : (
          <PageClient session={session} initialCollections={collections} />
        )}
      </div>
    </div>
  );
}

/**
 * Force dynamic rendering (no static optimization)
 */
export const dynamic = "force-dynamic";