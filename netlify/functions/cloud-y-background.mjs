// 云端精修（Y）的后台函数：下 B站 音频 → 豆包极速版识别 → 存稿。最长可跑 15 分钟。每一步都写进任务记录。
// 只处理 cloud.mjs 用口令建好、还在排队（queued）的任务，所以直接被人调用也做不了别的。
import { store, secrets, Bili, recognize, utterText, chars, Tracker, TASK_ID, pruneTasks } from "../lib/cloud.mjs";

export default async (req) => {
  let id;
  try { ({ id } = await req.json()); } catch { return; }
  if (typeof id !== "string" || !TASK_ID.test(id)) return;
  const st = store();
  const task = await st.get(`task/${id}`, { type: "json" });
  if (!task || task.status !== "running" || !task.queued) return;
  const tr = new Tracker(st, task);
  task.queued = false;
  try {
    await tr.enter("audio");
    const sec = await secrets();
    const audio = await (await new Bili(sec.bili).init()).audio(task.meta);
    if (audio.length > 67 * 1048576) throw new Error("音频太大（>67MB）");
    await tr.note("audio", `${(audio.length / 1048576).toFixed(1)} MB`);
    await tr.enter("asr");
    const utts = await recognize(audio, sec.volc);
    if (!utts.length) throw new Error("豆包没识别出内容");
    await tr.enter("save");
    const { text, extra } = utterText(utts);
    await st.setJSON(`doc/${task.bvid}`, { ...task.meta, mode: "Y", source: "豆包volc.seedasr.auc（云端）", text,
                                           chars: chars(text), ...extra, created: Date.now() });
    await tr.done({ chars: chars(text) });
  } catch (e) {
    await tr.fail(e);
  }
  await pruneTasks(st);
};
