import { NextResponse } from "next/server";

export async function GET() {
  const rawBackendUrl =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.BACKEND_URL ||
    "https://prism-backend-qboc.onrender.com";
  const backendUrl = rawBackendUrl.replace(/\/+$/, "");
  return NextResponse.json({ backendUrl });
}
