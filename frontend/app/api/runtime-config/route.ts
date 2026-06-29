// Exposes runtime configuration to the browser client. Read on the server at request time
// (NOT baked into the bundle), so one frontend image can target any backend by setting the
// BACKEND_API_URL env var. lib/api.ts fetches this once and caches it, falling back to the
// build-time NEXT_PUBLIC_API_URL when BACKEND_API_URL is unset (e.g. local dev).

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({
    apiUrl: process.env.BACKEND_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "",
  });
}
