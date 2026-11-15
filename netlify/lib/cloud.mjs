// 云端转写共用层：B站 取数、口令校验、豆包识别、成稿。给 functions/cloud.mjs 和 cloud-y-background.mjs 用。
// 实测（Netlify us-east-2）：view 接口不带设备指纹 cookie 会 412；带上 buvid3/buvid4 就通。
// 音频 CDN 不带 Range 头时偶发 567，所以一律带 Range，主镜像不行换备用镜像。
// 豆包极速版直接吃 B站 原始 dash m4a，不用转码。
import { createHash, timingSafeEqual } from "node:crypto";
import { getStore } from "@netlify/blobs";

export const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36";
const REF = "https://www.bilibili.com/";
const MIX = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,
  37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52];
const md5 = (s) => createHash("md5").update(s).digest("hex");
const sha256 = (s) => createHash("sha256").update(s).digest("hex");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const PRICE = 0.8;            // 元/小时
export const MAX_SEC = 7200;         // 极速版上限 2 小时
const DOUBAO = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash";
const RESOURCE = "volc.seedasr.auc";

export const store = () => getStore({ name: "zhuanxie-cloud", consistency: "strong" });
const vault = () => getStore({ name: "zhuanxie-secrets", consistency: "strong" });

export const json = (b, s = 200) => new Response(JSON.stringify(b), {
  status: s, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
});

// 密钥放在 Blobs（Mac 上 cloud-secrets.sh 写入）：{ bili:{sessdata,bili_jct,dede_user_id}, volc, pass_sha256 }
export async function secrets() {
  const s = await vault().get("all", { type: "json" });
  if (!s || !s.bili || !s.volc || !s.pass_sha256) throw new Error("云端还没配密钥：在 Mac 上跑一次 cloud-secrets.sh");
  return s;
}

// 口令：按来访 IP 计失败次数，一小时内错 10 次就锁（防止有人翻到页面后硬猜）
export async function checkPass(pass, sec, ip = "?") {
  const st = store(), k = `fails/${ip}`;
  const f = (await st.get(k, { type: "json" })) || { n: 0, t: 0 };
  const fresh = Date.now() - f.t < 3600e3;
  if (fresh && f.n >= 10) return "locked";
  const a = Buffer.from(sha256(String(pass || "")), "hex"), b = Buffer.from(sec.pass_sha256, "hex");
  if (a.length === b.length && timingSafeEqual(a, b)) { if (f.n) await st.delete(k); return "ok"; }
  await st.setJSON(k, { n: (fresh ? f.n : 0) + 1, t: Date.now() });
  return "bad";
}

export const bjDate = (ts) => (ts ? new Date((ts + 8 * 3600) * 1000).toISOString().slice(0, 10) : "");

export class Bili {
  constructor(b) { this.login = `SESSDATA=${b.sessdata}; bili_jct=${b.bili_jct}; DedeUserID=${b.dede_user_id}`; }

  async init() {   // 领设备指纹：没有它 view 接口在海外机房会 412
    try {
      const d = (await (await fetch("https://api.bilibili.com/x/frontend/finger/spi", { headers: { "User-Agent": UA } })).json()).data || {};
      this.cookie = `${this.login}; buvid3=${d.b_3 || ""}; buvid4=${encodeURIComponent(d.b_4 || "")}`;
    } catch { this.cookie = this.login; }
    return this;
  }

  async get(url, tries = 3) {
    let last;
    for (let i = 0; i < tries; i++) {
      try {
        const r = await fetch(url, { headers: { "User-Agent": UA, Referer: REF, Cookie: this.cookie } });
        if (r.status === 412) throw new Error("B站 风控拦截（412）");
        return await r.json();
      } catch (e) { last = e; await sleep(700 * (i + 1)); }
    }
    throw last;
  }

  async wbi(p) {
    if (!this.mk) {
      const n = (await this.get("https://api.bilibili.com/x/web-interface/nav")).data.wbi_img;
      const raw = n.img_url.split("/").pop().split(".")[0] + n.sub_url.split("/").pop().split(".")[0];
      this.mk = MIX.map((i) => raw[i]).join("").slice(0, 32);
    }
    p = { ...p, wts: Math.floor(Date.now() / 1000) };
    const q = Object.keys(p).sort()
      .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(p[k]).replace(/[!'()*]/g, ""))}`).join("&");
    return q + "&w_rid=" + md5(q + this.mk);
  }

  async bvid(input) {   // BV / b23.tv 短链 / av 号 → BV
    const s = String(input || "").trim();
    let m = s.match(/BV[0-9A-Za-z]{10}/);
    if (m) return m[0];
    const short = s.match(/https?:\/\/(?:b23\.tv|bili2233\.cn)\/[0-9A-Za-z]+/);
    let tail = s;
    if (short) {
      const r = await fetch(short[0], { redirect: "manual", headers: { "User-Agent": UA } });
      tail = r.headers.get("location") || "";
      m = tail.match(/BV[0-9A-Za-z]{10}/);
      if (m) return m[0];
    }
    const av = tail.match(/(?:^|[^a-z])av(\d+)/i);
    if (av) {
      const d = await this.get(`https://api.bilibili.com/x/web-interface/view?aid=${av[1]}`);
      if (d.code === 0) return d.data.bvid;
    }
    throw new Error("没认出 B站 视频链接（番剧、合集请用 Mac 转）");
  }

  async meta(bvid) {
    const d = await this.get(`https://api.bilibili.com/x/web-interface/view?bvid=${bvid}`);
    if (d.code !== 0) throw new Error(`取视频信息失败：${d.code} ${d.message || ""}`);
    const v = d.data;
    return { bvid: v.bvid, aid: v.aid, cid: v.cid || v.pages?.[0]?.cid, title: v.title,
             up: v.owner?.name || "未知", pub: bjDate(v.pubdate), dur: v.duration || 0 };
  }

  // 平台字幕：只认中文轨，官方 CC 优先于 AI 字幕（同 src/bili.py）
  async subtitle(m) {
    const d = await this.get("https://api.bilibili.com/x/player/wbi/v2?" + await this.wbi({ aid: m.aid, cid: m.cid }));
    if (d.code !== 0) throw new Error(`字幕接口失败：${d.code}`);
    if (d.data?.need_login_subtitle && !d.data?.login_mid) throw new Error("云端的 B站 登录已过期：在 Mac 上跑 refresh-cookie.sh");
    const tracks = d.data?.subtitle?.subtitles || [];
    let t = null;
    for (const lan of ["zh-CN", "zh-Hans", "zh", "ai-zh"]) { t = tracks.find((x) => x.lan === lan); if (t) break; }
    t = t || tracks.find((x) => /^(zh|ai-zh)/i.test(String(x.lan || "")));
    if (!t) return null;
    const url = t.subtitle_url.startsWith("//") ? "https:" + t.subtitle_url : t.subtitle_url;
    const body = ((await this.get(url)).body || [])
      .map((b) => ({ ...b, content: String(b.content || "").replace(/<[^>]{1,20}>/g, "").trim() }));
    return { lan: t.lan, paras: subParagraphs(body) };
  }

  async audio(m) {   // 最低码率音轨（约 64kbps，1 小时 ≈ 29MB），原样返回 m4a 字节
    const d = await this.get("https://api.bilibili.com/x/player/wbi/playurl?" +
      await this.wbi({ bvid: m.bvid, cid: m.cid, fnval: 16, fnver: 0, fourk: 0 }));
    const a = (d.data?.dash?.audio || []).sort((x, y) => x.bandwidth - y.bandwidth)[0];
    if (!a) throw new Error(`取不到音频流：${d.code} ${d.message || ""}`);
    const urls = [a.baseUrl || a.base_url, ...(a.backupUrl || a.backup_url || [])];
    for (const url of urls) {
      for (let i = 0; i < 2; i++) {
        try {
          const r = await fetch(url, { headers: { "User-Agent": UA, Referer: REF, Range: "bytes=0-" } });
          if (r.status === 200 || r.status === 206) {
            const b = Buffer.from(await r.arrayBuffer());
            if (b.length > 10000) return b;
          }
        } catch {}
        await sleep(1000);
      }
    }
    throw new Error("音频下载失败（各镜像都不行）");
  }
}

// 同 src/bili.py paragraphs：停顿 >1.2 秒或攒够 320 字断段
export function subParagraphs(body, gap = 1.2, maxlen = 320) {
  const paras = []; let cur = [], prev = null;
  for (const it of body) {
    const c = (it.content || "").trim(); if (!c) continue;
    const n = cur.reduce((s, x) => s + x.length, 0);
    if (cur.length && ((prev !== null && (it.from || 0) - prev > gap) || n > maxlen)) { paras.push(cur.join(" ")); cur = []; }
    cur.push(c); prev = it.to || 0;
  }
  if (cur.length) paras.push(cur.join(" "));
  return paras;
}

export async function recognize(audio, key, tries = 2) {
  const body = JSON.stringify({
    user: { uid: "transcribe-cloud" }, audio: { data: audio.toString("base64") },
    request: { model_name: "bigmodel", enable_punc: true, enable_itn: true, enable_ddc: true, enable_speaker_info: true },
  });
  let last;
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(DOUBAO, { method: "POST", body, headers: {
        "X-Api-Key": key, "X-Api-Resource-Id": RESOURCE, "X-Api-Sequence": "-1",
        "X-Api-Request-Id": crypto.randomUUID(), "Content-Type": "application/json" } });
      const sc = r.headers.get("x-api-status-code");
      if (sc !== "20000000") throw new Error(`豆包 ${sc} ${r.headers.get("x-api-message") || ""}`);
      return (await r.json()).result?.utterances || [];
    } catch (e) { last = e; await sleep(4000 * (i + 1)); }
  }
  throw last;
}

// 豆包分句 → 正文。单人口播不标说话人；多人用「说话人A/B」，开场说「大家好」的记为主持人。
// 零散说话人（<2% 字数）并入前一句的说话人（同 src/merge.py combine）。
export function utterText(utts) {
  const rows = utts.map((u) => ({ t: (u.start_time || 0) / 1000, s: String(u.additions?.speaker ?? "?"), x: u.text || "" }))
    .filter((r) => r.x.trim());
  const tot = rows.reduce((n, r) => n + r.x.length, 0) || 1;
  const share = {};
  for (const r of rows) share[r.s] = (share[r.s] || 0) + r.x.length / tot;
  const minor = new Set(Object.keys(share).filter((s) => share[s] < 0.02));
  rows.forEach((r, k) => { if (minor.has(r.s)) r.s = k ? rows[k - 1].s : (rows.find((x) => !minor.has(x.s))?.s ?? r.s); });
  const top = Math.max(...Object.entries(share).filter(([s]) => !minor.has(s)).map(([, v]) => v), 0);
  if (top >= 0.85) {   // 单人：README 坑 7——单人口播常被分出一个占一成的「第二人」
    const paras = []; let buf = [], prev = null;
    for (const r of rows) {
      const n = buf.reduce((s, x) => s + x.length, 0);
      if (buf.length && (n > 420 || (prev !== null && r.t - prev > 2 && n >= 150))) { paras.push(buf.join(" ")); buf = []; }
      buf.push(r.x); prev = r.t;
    }
    if (buf.length) paras.push(buf.join(" "));
    return { text: paras.join("\n\n"), extra: { paragraphs: paras.length } };
  }
  const names = {}; let host = null;
  for (const r of rows.slice(0, 8)) if (r.x.includes("大家好")) { host = r.s; names[r.s] = "主持人"; break; }
  let n = 0;
  for (const r of rows) if (!(r.s in names)) names[r.s] = "说话人" + "ABCDEFGH"[n++] ;
  const turns = []; let cur = null, buf = [];
  for (const r of rows) {
    const w = names[r.s];
    if (w !== cur) { if (buf.length) turns.push([cur, buf.join(" ")]); cur = w; buf = [r.x]; } else buf.push(r.x);
  }
  if (buf.length) turns.push([cur, buf.join(" ")]);
  return { text: turns.map(([w, t]) => `**${w}**：${t}`).join("\n\n"),
           extra: { turns: turns.length, speakers: [...new Set(Object.values(names))].join(" / ") } };
}

export const chars = (text) => text.replace(/\*\*[^*]+\*\*：/g, "").replace(/\s/g, "").length;
export const docHead = (d) => ({ bvid: d.bvid, title: d.title, up: d.up, pub: d.pub, dur: d.dur, chars: d.chars, mode: d.mode, from: d.from || "cloud", created: d.created });

// ── 任务记录：每次转写（网页云端、Mac 热键）都留一份，分步记 ✓/✗/耗时，失败时写清原因和怎么办 ──
// 存 task/<id>；首页「最近任务」和任务页 t.html 读它。
export const STEPS = {
  T: [["link", "读链接"], ["meta", "解析视频"], ["sub", "取字幕"], ["save", "存稿"]],
  Y: [["link", "读链接"], ["meta", "解析视频"], ["audio", "下载音频"], ["asr", "豆包识别"], ["save", "存稿"]],
};
export const TASK_ID = /^[\w-]{6,60}$/;

export function newTask(src, mode, url) {
  return { id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`, src, mode,
           url: String(url || "").slice(0, 300), status: "running", t0: Date.now(), t: Date.now(),
           steps: STEPS[mode].map(([k, name]) => ({ k, name, s: "wait" })) };
}

// 失败原因 → 白话原因 + 一句怎么办（Mac 端 src/task.py 里有同一张表的 Python 版）
export function explain(msg) {
  const m = String(msg || "");
  const rules = [
    [/没有中文字幕|no_sub/, "这条视频没有中文字幕，免费模式出不了稿", "改用 Y 精修"],
    [/登录已过期|need_login/i, "B站 登录过期", "在 Mac 上跑 ~/Documents/转写库/setup/refresh-cookie.sh"],
    [/412|风控/, "B站 风控拦截了这次请求", "过几分钟再试"],
    [/豆包 4|豆包 5|X-Api|API Key/i, "豆包拒绝了请求（Key 无效、没开通或余额不足）", "去火山引擎控制台看 API Key 和余额"],
    [/超过 2 小时|too_long/, "视频超过 2 小时，云端转不了", "回 Mac 按 ⌃⌘Y"],
    [/音频太大/, "音频太大，云端处理不了", "回 Mac 按 ⌃⌘Y"],
    [/音频下载失败|取不到音频/, "音频下载失败", "再试一次；还不行回 Mac 按 ⌃⌘Y"],
    [/没认出|番剧/, "没认出 B站 视频链接", "复制视频页地址再试（番剧、合集请用 Mac）"],
    [/没配密钥|not_configured/, "云端还没配密钥", "在 Mac 上跑 ~/Documents/转写库/setup/cloud-secrets.sh"],
    [/timeout|timed out|fetch failed|ETIMEDOUT|ECONNRESET|network/i, "网络不通或超时", "再试一次（做完的步骤会复用，不重复扣费）"],
  ];
  for (const [re, r, f] of rules) if (re.test(m)) return [r, f];
  return ["没预料到的错误：" + m.slice(0, 80), "再试一次；还不行把这一页截图发给 Claude"];
}

export class Tracker {
  constructor(st, task) { this.st = st; this.task = task; }
  async save() { this.task.t = Date.now(); await this.st.setJSON(`task/${this.task.id}`, this.task); }
  #close() {
    for (const s of this.task.steps) if (s.s === "run") { s.s = "ok"; s.ms = Date.now() - s.t0; }
  }
  async enter(k, note) {
    this.#close();
    const s = this.task.steps.find((x) => x.k === k);
    if (s) { s.s = "run"; s.t0 = Date.now(); if (note) s.note = note; }
    await this.save();
  }
  async note(k, note) { const s = this.task.steps.find((x) => x.k === k); if (s) s.note = note; await this.save(); }
  async done(extra = {}) {
    this.#close();
    for (const s of this.task.steps) if (s.s === "wait") s.s = "skip";
    Object.assign(this.task, extra, { status: "done" });
    await this.save();
  }
  async fail(err) {
    const s = this.task.steps.find((x) => x.s === "run") || this.task.steps.find((x) => x.s === "wait");
    if (s) { s.s = "fail"; if (s.t0) s.ms = Date.now() - s.t0; }
    const [reason, fix] = explain(err?.message || err);
    Object.assign(this.task, { status: "error", reason, fix, msg: String(err?.message || err).slice(0, 300) });
    await this.save();
  }
}

// 只留最近 60 条任务
export async function pruneTasks(st) {
  const { blobs } = await st.list({ prefix: "task/" });
  if (blobs.length <= 60) return;
  const all = (await Promise.all(blobs.map((b) => st.get(b.key, { type: "json" })))).filter(Boolean).sort((a, b) => a.t - b.t);
  await Promise.all(all.slice(0, all.length - 60).map((t) => st.delete(`task/${t.id}`)));
}
