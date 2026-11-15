// 云端转写入口（网页上的备用输入框调这里）。Mac 热键坏了、授权出问题时用。
//   POST {url, mode:"info"|"T"|"Y", pass}   要口令。T 当场出稿；Y 交给后台函数，返回 job
//   GET  ?job=<id>    Y 的进度        GET ?list    云端出过的稿（只要元数据）        GET ?doc=<BV>   一篇全文
// 稿子存 Blobs「zhuanxie-cloud」的 doc/<BV>；Mac 下次 publish.py 时收进 文稿/，随静态站发布。
import { store, secrets, checkPass, Bili, json, chars, docHead, PRICE, MAX_SEC } from "../lib/cloud.mjs";

export const config = { path: "/api/cloud" };

export default async (req, context) => {
  const u = new URL(req.url), st = store();

  if (req.method === "GET") {
    if (u.searchParams.has("list")) {
      const { blobs } = await st.list({ prefix: "doc/" });
      const docs = (await Promise.all(blobs.map((b) => st.get(b.key, { type: "json" })))).filter(Boolean).map(docHead);
      return json({ docs: docs.sort((a, b) => b.created - a.created) });
    }
    const bv = u.searchParams.get("doc");
    if (bv) {
      const d = /^BV[0-9A-Za-z]{10}$/.test(bv) && (await st.get(`doc/${bv}`, { type: "json" }));
      return d ? json(d) : json({ error: "not_found" }, 404);
    }
    const id = u.searchParams.get("job");
    if (id) {
      const j = /^[\w-]{6,60}$/.test(id) && (await st.get(`job/${id}`, { type: "json" }));
      return j ? json({ status: j.status, msg: j.msg, bvid: j.bvid, title: j.meta?.title }) : json({ error: "not_found" }, 404);
    }
    return json({ error: "bad_request" }, 400);
  }
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  let body;
  try { body = await req.json(); } catch { return json({ error: "bad_json" }, 400); }
  let sec;
  try { sec = await secrets(); } catch (e) { return json({ error: "not_configured", msg: e.message }, 503); }
  const ok = await checkPass(body.pass, sec, context?.ip);
  if (ok === "locked") return json({ error: "locked", msg: "口令错太多次，一小时后再试" }, 429);
  if (ok !== "ok") return json({ error: "bad_pass", msg: "口令不对" }, 401);

  try {
    const bili = await new Bili(sec.bili).init();
    const m = await bili.meta(await bili.bvid(body.url));
    const cost = +((m.dur / 3600) * PRICE).toFixed(2);
    const have = await st.get(`doc/${m.bvid}`, { type: "json" });

    if (body.mode === "info") return json({ ok: true, meta: m, cost, have: have?.mode || null });

    if (body.mode === "T") {
      if (have?.mode === "Y") return json({ ok: true, done: true, bvid: m.bvid, title: m.title, note: "已有精修版，免费模式不覆盖它" });
      const r = await bili.subtitle(m);
      if (!r || !r.paras.length) return json({ error: "no_sub", msg: "这条视频没有中文字幕，免费模式出不了稿，改用 Y" }, 422);
      const text = r.paras.join("\n\n");
      await st.setJSON(`doc/${m.bvid}`, { ...m, mode: "T", source: `${r.lan}（云端）`, text, chars: chars(text), created: Date.now() });
      return json({ ok: true, done: true, bvid: m.bvid, title: m.title });
    }

    if (body.mode === "Y") {
      if (m.dur > MAX_SEC) return json({ error: "too_long", msg: "超过 2 小时，云端转不了，请用 Mac" }, 422);
      const id = `${m.bvid}-${Date.now().toString(36)}`;
      await st.setJSON(`job/${id}`, { id, bvid: m.bvid, meta: m, status: "queued", msg: "排队中", t: Date.now() });
      const r = await fetch(new URL("/.netlify/functions/cloud-y-background", req.url), { method: "POST", body: JSON.stringify({ id }) });
      if (r.status !== 202) return json({ error: "bg_failed", msg: `后台任务没启动（${r.status}）` }, 502);
      return json({ ok: true, job: id, bvid: m.bvid, title: m.title, cost });
    }
    return json({ error: "bad_mode" }, 400);
  } catch (e) {
    return json({ error: "failed", msg: String(e?.message || e).slice(0, 200) }, 502);
  }
};
