#!/usr/bin/env python3
"""质检三件套：结构四道闸、孤词清单、双源分歧。
注意：豆包的 word.confidence 实测恒为 0，不可用作告警，故以「分歧」代替置信度。"""
import re, bisect, difflib, collections

# ── 一、结构四道闸（沿用语料库踩过的坑）──────────────────
def loop_ratio(lines, look=6):
    if len(lines) < 10: return 0.0
    dup = sum(1 for i, l in enumerate(lines) if l and l in lines[max(0, i-look):i])
    return round(dup / len(lines), 3)

def gates(text, lines, tail_end, dur):
    chars = len(re.sub(r'\s', '', text))
    cps = round(chars / dur, 3) if dur else 0
    lr = loop_ratio(lines)
    tail = round(tail_end / dur, 3) if dur else 0
    bad = []
    if chars < 200: bad.append('过短')
    if cps < 1.5: bad.append(f'密度低{cps}')
    if lr > 0.25: bad.append(f'循环{lr}')
    if tail < 0.90: bad.append(f'尾部截断{tail}')
    return {'chars': chars, 'cps': cps, 'loop': lr, 'tail': tail,
            'qc': 'pass' if not bad else 'warn', 'bad': bad}

# ── 二、孤词：只出现一次的英文词，识别错误高发区 ──────────
def lone_words(text, minlen=3):
    cnt = collections.Counter(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", text))
    lone = sorted(w for w, n in cnt.items() if n == 1 and len(w) >= minlen)
    def ctx(w):
        m = re.search(rf'.{{0,30}}\b{re.escape(w)}\b.{{0,30}}', text, re.I)
        return re.sub(r'\s+', ' ', m.group()).strip() if m else ''
    return [(w, ctx(w)) for w in lone], sum(cnt.values()), len(cnt)

# ── 三、双源分歧：两套独立转写打架的地方 ────────────────
FILL = re.compile(r'[呃嗯啊哦诶哎嘛呀吧]')
def _norm(s): return FILL.sub('', re.sub(r'[^\w一-鿿]', '', s)).lower()

def divergence(text_a, text_b, K=10, minlen=2, maxlen=24, ratio=3.0, gap=6):
    """锚点对齐后取「实词替换」型分歧。固定时间窗对齐不可靠，故用内容锚点。"""
    A, B = _norm(text_a), _norm(text_b)
    ca = collections.Counter(A[i:i+K] for i in range(len(A)-K))
    cb = collections.Counter(B[i:i+K] for i in range(len(B)-K))
    pairs = sorted((A.find(g), B.find(g)) for g in ca if ca[g] == 1 and cb.get(g) == 1)
    if not pairs: return []
    tails, idx, par = [], [], [None]*len(pairs)      # 单调递增子序列，剔除错位锚点
    for i, (_, y) in enumerate(pairs):
        j = bisect.bisect_left(tails, y)
        if j == len(tails): tails.append(y); idx.append(i)
        else: tails[j] = y; idx[j] = i
        par[i] = idx[j-1] if j else None
    seq, cur = [], (idx[-1] if idx else None)
    while cur is not None: seq.append(pairs[cur]); cur = par[cur]
    anchors = seq[::-1]
    out, pa, pb = [], 0, 0
    for x, y in anchors + [(len(A), len(B))]:
        sa, sb = A[pa:x], B[pb:y]
        if sa != sb:
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                    None, sa, sb, autojunk=False).get_opcodes():
                la, lb = i2-i1, j2-j1
                if tag == 'replace':
                    if la < minlen or lb < minlen: continue
                    # 一边远长于另一边 = 锚点缺口造成的对齐错位，不是实词分歧
                    if max(la, lb) > maxlen or max(la, lb) / min(la, lb) > ratio: continue
                    out.append({'kind': '替换', 'pos': pa+i1, 'a': sa[i1:i2], 'b': sb[j1:j2],
                                'ctx': A[max(0, pa+i1-20):pa+i1]})
                elif tag in ('delete', 'insert') and max(la, lb) >= gap:
                    # 单侧整段缺失。≥gap 字不可能是顺滑掉的语气词，是真的少了内容。
                    out.append({'kind': 'A缺' if tag == 'insert' else 'B缺', 'pos': pa+i1,
                                'a': sa[i1:i2], 'b': sb[j1:j2],
                                'ctx': A[max(0, pa+i1-20):pa+i1]})
        pa, pb = x, y
    return out

NEG = re.compile(r'[不没无非未别]')
def negation_check(text_a, text_b, span=40):
    """否定词专查：一字之差可翻转语义，普通阈值(minlen=2/gap=6)必然漏掉。
    只报两边否定词数量不一致的差异块，不受长度阈值限制。"""
    A, B = _norm(text_a), _norm(text_b)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, A, B, autojunk=False).get_opcodes():
        if tag == 'equal': continue
        sa, sb = A[i1:i2], B[j1:j2]
        if len(sa) > span or len(sb) > span: continue      # 过长=对齐错位
        if len(NEG.findall(sa)) != len(NEG.findall(sb)):
            out.append({'kind': '否定', 'pos': i1, 'a': sa, 'b': sb,
                        'ctx': A[max(0, i1-16):i1]})
    return out

CN = str.maketrans('零〇一二三四五六七八九', '00123456789')
def _nums(t):
    t = t.translate(CN)
    return collections.Counter(re.findall(r'\d+(?:\.\d+)?', t))

def number_check(text_a, text_b, minlen=2):
    """数字无语义冗余，错了读不出来。只报一边有、另一边没有的数字。"""
    na, nb = _nums(text_a), _nums(text_b)
    out = []
    for v in sorted(set(na) | set(nb), key=lambda x: (-len(x), x)):
        if len(v) < minlen: continue
        if na.get(v, 0) != nb.get(v, 0):
            out.append({'kind': '数字', 'v': v, 'a': na.get(v, 0), 'b': nb.get(v, 0)})
    return out

# ── 待核清单 ────────────────────────────────────────
def review_md(title, lone, nwords, nuniq, div=None, doubt=None, neg=None, num=None):
    L = [f'# 待核清单 — {title}', '',
         f'英文词 {nwords} 个 / 去重 {nuniq} 个，**只出现 1 次的 {len(lone)} 个**。',
         '重复出现的词基本正确，孤词与双源分歧是识别错误的高发区。',
         '核实后把结论写进 `tables/fix/<UP主>.json`，同一 UP 主下次不再错。', '']
    if doubt:
        L += ['## 〇、已存疑（未改正文，优先核）', '']
        L += [f'- **{w}** — {g}' for w, g in doubt.items()] + ['']
    if div:
        L += [f'## 一、双源分歧 {len(div)} 处（B站字幕 ⟷ 豆包）', '',
              '两套独立系统在同一处给出不同实词，至少有一边错。', '',
              '`A缺`/`B缺` = 单侧整段缺失（≥6 字），比听错更危险：文字仍然通顺，四道闸查不出。', '',
              '| 类型 | 上下文 | 源A | 源B |', '|---|---|---|---|']
        for d in sorted(div, key=lambda d: -(len(d['a'])+len(d['b'])))[:150]:
            k = d.get('kind', '替换')
            L.append(f"| {k} | …{d['ctx'][-16:]} | `{d['a'][:30] or '—'}` | `{d['b'][:30] or '—'}` |")
        L.append('')
    if neg:
        L += [f'## 一·五、否定词分歧 {len(neg)} 处（一字可翻转语义，普通阈值查不出）', '',
              '| 上下文 | 源A | 源B |', '|---|---|---|']
        L += [f"| …{d['ctx'][-16:]} | `{d['a'][:30] or '—'}` | `{d['b'][:30] or '—'}` |" for d in neg]
        L.append('')
    if num:
        L += [f'## 一·七、数字分歧 {len(num)} 处（数字无冗余，读不出来）', '',
              '| 数字 | 源A 出现 | 源B 出现 |', '|---|---|---|']
        L += [f"| `{d['v']}` | {d['a']} | {d['b']} |" for d in num] + ['']
    L += [f'## 二、孤词 {len(lone)} 个', '']
    L += [f'- `{w}` — …{c}…' for w, c in lone]
    return '\n'.join(L) + '\n'
