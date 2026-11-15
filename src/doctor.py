#!/usr/bin/env python3
"""对账：找出失败留下的残骸和不一致。

  src/doctor.py           只报告
  src/doctor.py --fix     能自动修的修掉（补发布、删孤儿缓存），删文稿仍要人确认

检查六项：
  1 文稿有、站上没有       → 发布失败或没发布过
  2 站上有、文稿没了       → 文稿被删但没重新发布
  3 .work 有缓存、没文稿   → ASR 跑了一半挂掉的残骸
  4 缓存段数不全           → 下次 --review 会崩
  5 库里有音频残留         → 临时文件没清干净
  6 hotkey.log 近期失败    → 热键静默失败过
"""
import sys, re, json, shutil, pathlib, argparse, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS, WORK, SITE = ROOT / '文稿', ROOT / '.work', ROOT / 'site'
sys.path.insert(0, str(ROOT / 'src'))

log = lambda *a: print(*a, flush=True)


ALIAS = set()      # 合并进别的文稿的那几期：有文稿、有缓存，但站上没有单独一页


def docs():
    """→ {bvid: (path, 时长秒)}"""
    out = {}
    for p in DOCS.rglob('*.md'):
        t = p.read_text(encoding='utf-8')[:1200]
        bv = re.search(r'^(?:bvid|id): (\S+)', t, re.M)       # 整理稿没有 B站 号，用 id
        dur = re.search(r'^duration: (?:(\d+)h)?(\d+)m(?:(\d+)s)?', t, re.M)
        if bv:
            s = 0
            if dur:
                s = int(dur.group(1) or 0) * 3600 + int(dur.group(2)) * 60 + int(dur.group(3) or 0)
            out[bv.group(1)] = (p, s)
            mg = re.search(r'^merged: (\S+)', t, re.M)          # 合并稿：其余几期也算有文稿（缓存不是孤儿）
            if mg:                                              # 合并稿的总时长不能拿来估单期缓存段数
                out[bv.group(1)] = (p, 0)
            for other in (mg.group(1).split(',') if mg else []):
                out.setdefault(other, (p, 0)); ALIAS.add(other)
    return out


def published():
    """站上已有的 bvid（小写）"""
    d = SITE / 'd'
    return {p.stem for p in d.glob('*.html')} if d.exists() else set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fix', action='store_true')
    ap.add_argument('--quiet', action='store_true',
                    help='只输出一行待处理摘要，给热键用；无问题则不输出')
    a = ap.parse_args()

    D, P = docs(), published()
    issues, fixable = [], []

    # 1 / 2 文稿 ↔ 站点 对账
    miss = sorted(bv for bv in D if bv.lower() not in P and bv not in ALIAS)
    if miss:
        issues.append(('未发布', f'{len(miss)} 篇文稿站上没有', [D[b][0].name for b in miss]))
        fixable.append('publish')
    ghost = sorted(P - {b.lower() for b in D})
    if ghost:
        issues.append(('站上多余', f'{len(ghost)} 篇站上有但文稿已删', ghost))
        fixable.append('publish')

    # 3 / 4 .work 残骸
    orphan, partial = [], []
    for w in sorted(WORK.glob('BV*')):
        segs = sorted(w.glob('seg*.json'))
        bv = w.name
        if bv not in D:
            orphan.append(f'{bv}（{len(segs)} 段缓存，无文稿）')
        elif segs:
            need = max(1, -(-D[bv][1] // 3600)) if D[bv][1] else 1
            if len(segs) < need:
                partial.append(f'{bv}（{len(segs)}/{need} 段，--review 会崩）')
    if orphan:
        issues.append(('孤儿缓存', f'{len(orphan)} 个，出稿失败留下的', orphan))
        fixable.append('rmwork')
    if partial:
        issues.append(('缓存不全', f'{len(partial)} 个，重出会崩', partial))
        fixable.append('rmwork')

    # 5 音频残留
    au = [p for p in ROOT.rglob('*') if p.suffix in ('.m4a', '.mp3', '.wav', '.webm')]
    if au:
        issues.append(('音频残留', f'{len(au)} 个，临时文件没清干净',
                       [f'{p.relative_to(ROOT)} ({p.stat().st_size//1024} KB)' for p in au]))
        fixable.append('rmaudio')

    # 6 近期失败
    lg = WORK / 'hotkey.log'
    if lg.exists():
        blocks = lg.read_text(encoding='utf-8', errors='replace').split('── ')[-8:]
        bad = [b.split('\n')[0][:19] + '  ' + next(
            (l.strip()[:60] for l in b.split('\n')
             if 'Traceback' in l or 'Error' in l or l.strip().startswith('!')), '')
            for b in blocks if ('Traceback' in b or 'Error' in b)]
        if bad:
            issues.append(('热键失败', f'最近 8 次里 {len(bad)} 次报错', bad))

    if a.quiet:
        # 历史日志不算「现在该处理的」，排除
        now = [(n, s) for n, s, _ in issues if n != '热键失败']
        if now:
            print(' · '.join(f'{n}:{s.split("，")[0]}' for n, s in now))
            return 1
        return 0

    if not issues:
        log(f'✅ 一切一致：文稿 {len(D)} 篇 · 站上 {len(P)} 篇 · 无残留')
        return 0

    log(f'发现 {len(issues)} 类问题：\n')
    for name, summary, items in issues:
        log(f'  【{name}】{summary}')
        for it in items[:6]:
            log(f'      · {it}')
        if len(items) > 6:
            log(f'      … 还有 {len(items)-6} 个')
        log('')

    if not a.fix:
        log('  跑 src/doctor.py --fix 自动修（删文稿仍需人确认）')
        return 1

    if 'rmaudio' in fixable:
        for p in au: p.unlink(missing_ok=True)
        log(f'  ✓ 删掉 {len(au)} 个音频残留')
    if 'rmwork' in fixable:
        n = 0
        for w in WORK.glob('BV*'):
            segs = list(w.glob('seg*.json'))
            if w.name not in D or (segs and w.name in D and
                                   len(segs) < max(1, -(-D[w.name][1] // 3600))):
                shutil.rmtree(w, ignore_errors=True); n += 1
        log(f'  ✓ 清掉 {n} 个残骸缓存')
    if 'publish' in fixable:
        log('  → 重新发布…')
        subprocess.run([str(ROOT / 'src' / 'publish.py')], cwd=ROOT)
    log('\n  再跑一次 doctor 确认')
    return 0


if __name__ == '__main__':
    sys.exit(main())
