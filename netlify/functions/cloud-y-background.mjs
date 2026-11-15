// 云端精修（Y）的后台函数：下 B站 音频 → 豆包极速版识别 → 成稿存 Blobs。最长可跑 15 分钟。
// 只处理 cloud.mjs 用口令建好、状态还是 queued 的任务，所以直接被人调用也做不了别的。
import { store, secrets, Bili, recognize, utterText, chars } from "../lib/cloud.mjs";

export default async (req) => {
  let id;
  try { ({ id } = await req.json()); } catch { return; }
  const st = store(), key = `job/${id}`;
  const job = typeof id === "string" && (await st.get(key, { type: "json" }));
  if (!job || job.status !== "queued") return;
  const set = (status, msg) => st.setJSON(key, { ...job, status, msg, t: Date.now() });
  try {
    await set("running", "下载音频…");
    const sec = await secrets();
    const audio = await (await new Bili(sec.bili).init()).audio(job.meta);
    if (audio.length > 67 * 1048576) throw new Error("音频太大（>67MB），请用 Mac");
    await set("running", `识别中…（音频 ${(audio.length / 1048576).toFixed(1)} MB）`);
    const utts = await recognize(audio, sec.volc);
    if (!utts.length) throw new Error("豆包没识别出内容");
    const { text, extra } = utterText(utts);
    await st.setJSON(`doc/${job.bvid}`, { ...job.meta, mode: "Y", source: "豆包volc.seedasr.auc（云端）", text,
                                          chars: chars(text), ...extra, created: Date.now() });
    await set("done", "完成");
  } catch (e) {
    await set("error", String(e?.message || e).slice(0, 200));
  }
};
