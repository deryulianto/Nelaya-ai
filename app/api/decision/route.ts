export const dynamic = "force-dynamic";
export const revalidate = 0;
export const runtime = "nodejs";

const RAW_BASE = process.env.FGI_API_BASE_URL || "http://127.0.0.1:8001";
const API_BASE = RAW_BASE.replace(/\/api\/v1\/fgi\/?$/, "");

export async function GET() {
  const url = `${API_BASE}/api/v1/decision?ts=${Date.now()}`;

  try {
    const res = await fetch(url, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });

    const text = await res.text();

    return new Response(text, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
      },
    });
  } catch (error: any) {
    return Response.json(
      {
        ok: false,
        error: "Proxy decision gagal.",
        detail: error?.message ?? String(error),
        target: url,
      },
      { status: 500 }
    );
  }
}
