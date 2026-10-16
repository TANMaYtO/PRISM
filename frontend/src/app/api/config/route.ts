import { NextResponse } from "next/server";

export async function GET() {
  const backendUrl = (process.env.API_URL || "").replace(/\/+$/, "");
  return NextResponse.json({ backendUrl });
}
