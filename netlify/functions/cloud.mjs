// 云端转写入口：网页「云端转写」框调这里；Mac 热键也往这里报进度、放稿子。
//   POST {url, mode:"info"|"T"|"Y", pass}         要口令。T 当场出稿；Y 交给后台函数。都返回 task（任务号）
//   POST {action:"task", task, pass}               Mac 热键上报任务进度（同一套任务记录）
//   POST {action:"putdoc", doc, pass}              Mac 出完稿放上站点「新稿」区，不用发布、不花额度
//   GET  ?task=<id>   一次任务的分步进度        GET ?tasks   最近 10 次任务
//   GET  ?list        站上「新稿」区的稿子      GET ?doc=<BV> 一篇全文
// 稿子存 Blobs「zhuanxie-cloud」的 doc/<BV>；Mac 下次 publish.py 时收进 文稿/，随静态站发布。
import { store, secrets, checkPass, Bili, json, chars, docHead, PRICE, MAX_SEC,
         newTask, Tracker, TASK_ID, pruneTasks } from "../lib/cloud.mjs";

export const config = { path: "/api/cloud" };
const BV = /^(BV[0-9A-Za-z]{10}|M\d{8}-[0-9a-f]{4,8})$/;   // B站 号，或整理稿编号

export default async (req, context) => {
  const u = new URL(req.url), st = store();

  if (req.method === "GET") {
    if (u.searchParams.has("list")) {
      const { blobs } = await st.list({ prefix: "doc/" });
      const docs = (await Promise.all(blobs.map((b) => st.get(b.key, { type: "json" })))).filter(Boolean).map(docHead);
      return json({ docs: docs.sort((a, b) => b.created - a.created) });
    }
    if (u.searchParams.has("tasks")) {
      const { blobs } = await st.list({ prefix: "task/" });
      const all = (await Promise.all(blobs.map((b) => st.get(b.key, { type: "json" })))).filter(Boolean);
      return json({ tasks: all.sort((a, b) => b.t0 - a.t0).slice(0, 10) });
    }
    const bv = u.searchParams.get("doc");
    if (bv) {
      const d = BV.test(bv) && (await st.get(`doc/${bv}`, { type: "json" }));
      return d ? json(d) : json({ error: "not_found" }, 404);
    }
    const id = u.searchParams.get("task");
    if (id) {
      const t = TASK_ID.test(id) && (await st.get(`task/${id}`, { type: "json" }));
      return t ? json(t) : json({ error: "not_found" }, 404);
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

  // ── Mac 热键上报 ──
  if (body.action === "task") {
    const t = body.task;
    if (!t || !TASK_ID.test(t.id) || !Array.isArray(t.steps) || JSON.stringify(t).length > 50000) return json({ error: "bad_task" }, 400);
    await st.setJSON(`task/${t.id}`, { ...t, src: "mac" });
    if (t.status !== "running") await pruneTasks(st);
    return json({ ok: true });
  }
  if (body.action === "putdoc") {
    const d = body.doc;
    if (!d || !BV.test(d.bvid) || typeof d.text !== "string" || d.text.length > 3e6) return json({ error: "bad_doc" }, 400);
    await st.setJSON(`doc/${d.bvid}`, { ...d, from: "mac", created: Date.now() });
    return json({ ok: true });
  }

  // ── 网页云端转写 ──
  const mode = body.mode;
  if (!["info", "T", "Y"].includes(mode)) return json({ error: "bad_mode" }, 400);
  const tr = mode === "info" ? null : new Tracker(st, newTask("cloud", mode, body.url));
  try {
    if (tr) await tr.enter("link");
    const bili = await new Bili(sec.bili).init();
    const bvid = await bili.bvid(body.url);
    if (tr) await tr.enter("meta");
    const m = await bili.meta(bvid);
    const cost = +((m.dur / 3600) * PRICE).toFixed(2);
    const have = await st.get(`doc/${m.bvid}`, { type: "json" });
    if (mode === "info") return json({ ok: true, meta: m, cost, have: have?.mode || null });
    Object.assign(tr.task, { bvid: m.bvid, title: m.title, up: m.up, dur: m.dur });

    if (mode === "T") {
      await tr.enter("sub");
      if (have?.mode === "Y") {
        await tr.done({ outcome: "已有精修版，没重出", note: "免费模式不覆盖精修版；要重出用 Y" });
        return json({ ok: true, task: tr.task.id });
      }
      const r = await bili.subtitle(m);
      if (!r || !r.paras.length) throw new Error("这条视频没有中文字幕");
      await tr.enter("save");
      const text = r.paras.join("\n\n");
      await st.setJSON(`doc/${m.bvid}`, { ...m, mode: "T", source: `${r.lan}（云端）`, text, chars: chars(text), created: Date.now() });
      await tr.done({ chars: chars(text) });
      await pruneTasks(st);
      return json({ ok: true, task: tr.task.id });
    }

    // Y：交给后台函数（最长 15 分钟）
    if (m.dur > MAX_SEC) throw new Error("超过 2 小时");
    tr.task.meta = m; tr.task.cost = cost; tr.task.queued = true;
    await tr.enter("audio", "排队中");
    const r = await fetch(new URL("/.netlify/functions/cloud-y-background", req.url), {
      method: "POST", body: JSON.stringify({ id: tr.task.id }) });
    if (r.status !== 202) throw new Error(`后台任务没启动（${r.status}）`);
    return json({ ok: true, task: tr.task.id, cost });
  } catch (e) {
    if (tr) { await tr.fail(e); return json({ ok: false, task: tr.task.id, error: "failed", msg: tr.task.reason }); }
    return json({ error: "failed", msg: String(e?.message || e).slice(0, 200) }, 502);
  }
};
