#!/usr/bin/env python3
"""把同一场访谈分成几期的文稿合并成一篇（上下集、Part 1/2…）。

  join.py <BV1> <BV2> [...] [--title 标题]

· 以第一期为主：用它的 B站 号、UP 主、发布日期；时长、字数、待核项相加；front matter 记 merged: 其余几期的 BV
· 正文按期顺序拼接，每期前面加一行「【上集】标题（日期 · B站 BV）」这样的分隔
· 合并后删掉其余几期的单独文稿，避免站上出现两份；它们的 .work 缓存保留（doctor 认 merged: 字段，不算孤儿）
· 改了 tables 想重出：先对每一期跑 ts.py --review <BV>（会重新生成单期文稿），再跑一遍 join.py 合并回去
"""
import re, sys, argparse, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ts

ROOT = pathlib.Path(__file__).resolve().parent.parent
PART = ['上集', '下集'] + [f'第{i}期' for i in range(3, 10)]


def find(bv):
    for p in (ROOT / '文稿').rglob('*.md'):
        t = p.read_text(encoding='utf-8')
        if re.search(rf'^(?:bvid|merged): .*\b{bv}\b', t[:1200], re.M):
            fm, body = re.match(r'---\n(.*?)\n---\n+(.*)', t, re.S).groups()
            return p, dict(l.split(': ', 1) for l in fm.splitlines() if ': ' in l), body.strip()
    raise SystemExit(f'找不到 {bv} 的文稿（先用 ts.py 转出来）')


def secs(d):
    m = re.match(r'(?:(\d+)h)?(\d+)m(?:(\d+)s)?', d or '')
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bvs', nargs='+')
    ap.add_argument('--title')
    a = ap.parse_args()
    if len(a.bvs) < 2:
        raise SystemExit('至少两期')
    parts = [find(bv) for bv in a.bvs]
    if any(fm.get('merged') for _, fm, _ in parts):          # 已经合并过：先拆不了，提示从单期重来
        raise SystemExit('其中有已经合并过的文稿；先对每一期 ts.py --review <BV> 重出单期，再合并')
    head = parts[0][1]
    blocks, dur, chars, unres, turns = [], 0, 0, 0, 0
    for i, ((p, fm, body), bv) in enumerate(zip(parts, a.bvs)):
        blocks.append(f'【{PART[i]}】{fm.get("title", "")}（{fm.get("published", "")} · B站 {bv}）')
        blocks.append(body)
        dur += secs(fm.get('duration')); chars += int(fm.get('chars') or 0)
        unres += int(fm.get('unresolved') or 0); turns += int(fm.get('turns') or 0)
    speakers = sorted({s.strip() for _, fm, _ in parts for s in fm.get('speakers', '').split('/') if s.strip()})
    meta = {'title': a.title or f"{head['title']}（上下集合并）", 'up': head.get('up'),
            'bvid': a.bvs[0], 'pub': head.get('published'), 'dur': dur}
    extra = {'merged': ','.join(a.bvs[1:]), 'source': head.get('source'), 'chars': chars,
             'turns': turns or None, 'speakers': ' / '.join(speakers) or None,
             'qc': 'pass' if all(fm.get('qc') == 'pass' for _, fm, _ in parts) else 'warn',
             'unresolved': unres}
    out = ts.write(meta, '\n\n'.join(blocks), extra)
    for p, _, _ in parts:
        if p != out:
            p.unlink(missing_ok=True)
    print(f'  ✓ 合并 {len(parts)} 期 → {out.relative_to(ROOT)}')
    print(f'    {dur // 60} 分钟 · {chars} 字 · 待核 {unres} 项；已删单期文稿：'
          + '、'.join(str(p.relative_to(ROOT)) for p, _, _ in parts if p != out))
    return out


if __name__ == '__main__':
    main()
