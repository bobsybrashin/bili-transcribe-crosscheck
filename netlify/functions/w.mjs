// 权重同步。GET 公开读，POST 要密钥（站点无访问保护，写入必须挡一道）。
import { getStore } from "@netlify/blobs";

const BLOB = "zhuanxie";
const DOC = "weights";
const MAX = 400_000;                       // 几百篇稿子的权重表也就几十 KB

const json = (b, s = 200) => new Response(JSON.stringify(b), {
  status: s,
  headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
});

export default async (req) => {
  const store = getStore(BLOB);

  if (req.method === "GET") {
    const doc = await store.get(DOC, { type: "json" });
    return json({ w: doc?.w ?? {}, at: doc?.at ?? 0 });
  }

  if (req.method === "POST") {
    const secret = process.env.ZHUANXIE_KEY;
    if (!secret) return json({ error: "server_not_configured" }, 500);
    const k = req.headers.get("x-key") || new URL(req.url).searchParams.get("k") || "";
    if (k !== secret) return json({ error: "unauthorized" }, 401);

    let body;
    try { body = await req.json(); } catch { return json({ error: "bad_json" }, 400); }
    if (!body || typeof body.w !== "object") return json({ error: "bad_shape" }, 400);
    const s = JSON.stringify({ w: body.w, at: Date.now() });
    if (s.length > MAX) return json({ error: "too_big" }, 413);
    await store.setJSON(DOC, JSON.parse(s));
    return json({ ok: true, at: JSON.parse(s).at });
  }

  return json({ error: "method_not_allowed" }, 405);
};

export const config = { path: "/api/w" };
