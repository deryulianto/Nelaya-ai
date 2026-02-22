// app/api/fgi/map-grid/latest/route.ts
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const RAW_BASE = (process.env.FGI_API_BASE_URL ?? "http://127.0.0.1:8001").replace(/\/+$/, "");
const API_BASE = RAW_BASE.endsWith("/api/v1/fgi") ? RAW_BASE : `${RAW_BASE}/api/v1/fgi`;

function copyUsefulHeaders(upstream: Response, res: NextResponse) {
  const allow = new Set([
    "content-type",
    "cache-control",
    "etag",
    "last-modified",
    "content-encoding",
    "vary",
  ]);
  upstream.headers.forEach((v, k) => {
    if (allow.has(k.toLowerCase())) res.headers.set(k, v);
  });
}

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const target = `${API_BASE}/map-grid/latest${url.search}`;

  const headers = new Headers(req.headers);
  headers.delete("host");

  const upstream = await fetch(target, {
    method: "GET",
    headers,
    cache: "no-store",
  });

  const body = await upstream.arrayBuffer();
  const res = new NextResponse(body, { status: upstream.status });

  copyUsefulHeaders(upstream, res);
  return res;
}
