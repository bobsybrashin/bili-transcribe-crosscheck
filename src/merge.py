#!/usr/bin/env python3
"""分段结果的说话人对齐与合并。分段识别的 speaker 编号不通用，必须靠重叠区对齐。"""
import difflib

# 与 asr 模块保持一致。写在这里而不是 import，是为了让本模块零依赖、可单独 copy 走。
SEG, OV = 3600, 60          # 段长 1h，重叠 60s 供说话人对齐

def cut(i, n):
    """段 i 保留的绝对时间区间。两侧必须用同一条线，否则接缝会重复约 OV*1.5 秒。"""
    return (-1 if i == 0 else i * SEG - OV / 2,
            (i + 1) * SEG - OV / 2 if i < n - 1 else float('inf'))

spk = lambda x: (x.get('additions') or {}).get('speaker', '?')

def align(segs, spans):
    """→ 每段的 raw→canonical 映射"""
    canon = [{s: s for s in {spk(x) for x in segs[0]}}]
    for i in range(1, len(segs)):
        lo, hi = spans[i][0], spans[i][0] + OV
        prev = [x for x in segs[i-1] if lo <= x['abs'] < hi]
        cur  = [x for x in segs[i]   if lo <= x['abs'] < hi]
        m = {}
        for s in sorted({spk(x) for x in cur}):
            ct = ''.join(x['text'] for x in cur if spk(x) == s)
            best, bs = s, -1.0
            for ps in sorted({spk(x) for x in prev}):
                pt = ''.join(x['text'] for x in prev if spk(x) == ps)
                r = difflib.SequenceMatcher(None, ct, pt).ratio()
                if r > bs: bs, best = r, canon[i-1].get(ps, ps)
            m[s] = best if bs > 0.15 else s
        canon.append(m)
    return canon

def combine(segs, spans, minor_ratio=0.02):
    """→ [(abs, speaker, text)]，已去重叠、已并零散说话人"""
    for (a, _), u in zip(spans, segs):
        for x in u: x['abs'] = a + x.get('start_time', 0) / 1000
    canon = align(segs, spans)
    out = []
    for i, u in enumerate(segs):
        lo, hi = cut(i, len(segs))
        out += [[x['abs'], canon[i].get(spk(x), spk(x)), x['text']]
                for x in u if lo <= x['abs'] < hi]
    out.sort(key=lambda z: z[0])
    tot = sum(len(t) for _, _, t in out) or 1
    minor = {s for s in {r[1] for r in out}
             if sum(len(t) for _, ss, t in out if ss == s) / tot < minor_ratio}
    for k, r in enumerate(out):
        if r[1] in minor: r[1] = out[k-1][1] if k else next(
            (x[1] for x in out if x[1] not in minor), r[1])
    return out

def name_speakers(rows, hint=None):
    """用开场白认主持人；hint=(主持人名, 嘉宾名)"""
    host, guest = hint or ('主持人', '嘉宾')
    m = {}
    for _, s, t in rows[:8]:
        if '大家好' in t or host in t: m[s] = host; break
    for _, s, _ in rows:
        if s not in m and len(m) < 2: m[s] = guest
    return m

def to_turns(rows, names, fix=()):
    turns, cur, buf = [], None, []
    for _, s, t in rows:
        for a, b in fix: t = t.replace(a, b)
        w = names.get(s, f'说话人{s}')
        if w != cur:
            if buf: turns.append((cur, ' '.join(buf)))
            cur, buf = w, [t]
        else: buf.append(t)
    if buf: turns.append((cur, ' '.join(buf)))
    return turns

def to_paragraphs(rows, fix=(), gap=2.0, minlen=150, maxlen=420):
    """单人口播：不标说话人。停顿只在已攒够 minlen 时才断，避免碎成一句一段。"""
    paras, buf, prev = [], [], None
    for t, _, txt in rows:
        for a, b in fix: txt = txt.replace(a, b)
        n = sum(len(x) for x in buf)
        if buf and (n > maxlen or (prev is not None and t - prev > gap and n >= minlen)):
            paras.append(' '.join(buf)); buf = []
        buf.append(txt); prev = t
    if buf: paras.append(' '.join(buf))
    return paras
