#!/usr/bin/env python3
"""转写库 CLI —— 给个链接出文稿。

  ts.py <url>              开跑前当面问走哪条路，把耗时和花费摆出来再选
  ts.py <url> --fast       快车道：平台字幕，约 1 秒，免费
  ts.py <url> --fine       精修：豆包 ASR + 双源核对，约 0.8 元/小时
  ts.py --review <BV>      走缓存重出，不花额度（改了 tables 后重出用它）
  ts.py --finalize <BV>    定稿：重出最终稿并删光过程文件

批量（合集 / UP主空间 / 系列链接）自动摊开，默认增量——已有文稿的跳过：
  ts.py <合集或UP主空间url>        增量，只补新的
  ts.py <同上> --all               连已有的一起重跑
  ts.py <同上> --fine --yes        批量精修，--yes 确认花费

单视频链接支持 BV / b23.tv 短链 / 番剧 ep·ss。

交付只有一份：文稿/<UP主>/<日期> <标题>.md
过程文件在 .work/<BV>/，定稿时删除。tables/ 是唯一长期资产。
"""
import sys, os, json, argparse, shutil, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import bili, fetch, asr, merge, qc

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / '.work'
SAFE = __import__('re').compile(r'[\\/:*?"<>|\n\r\t]')
safe = lambda s, n=60: SAFE.sub('', (s or '').strip())[:n].rstrip(' .')
log = lambda *a: print(*a, flush=True)


def ups():
    p = ROOT / 'tables' / 'ups.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def tables(up):
    hot, fix = [], []
    for kind, acc in (('hot', hot), ('fix', fix)):
        for name in ('_default', up):
            p = ROOT / 'tables' / kind / f'{name}.json'
            if p.exists(): acc.extend(json.loads(p.read_text(encoding='utf-8')))
    return hot, [tuple(x) for x in fix]


def final_path(meta):
    d = ROOT / '文稿' / safe(meta.get('up', '未知'), 40)
    return d / f"{meta.get('pub') or '0000-00-00'} {safe(meta['title'])}.md"


def write(meta, text, extra):
    p = final_path(meta); p.parent.mkdir(parents=True, exist_ok=True)
    fm = {'title': meta['title'], 'up': meta.get('up'), 'bvid': meta['bvid'],
          'published': meta.get('pub'),
          'duration': (f"{meta['dur']//3600}h{meta['dur']%3600//60}m" if meta['dur'] >= 3600
                       else f"{meta['dur']//60}m{meta['dur']%60}s"), **extra}
    p.write_text('---\n' + '\n'.join(f'{k}: {v}' for k, v in fm.items() if v not in (None, ''))
                 + '\n---\n\n' + text + '\n', encoding='utf-8')
    return p


def fast(meta):
    lan, body = fetch.subtitle(meta)
    if not lan: return None, None
    paras = bili.paragraphs(body)
    g = qc.gates(''.join(paras), [(b.get('content') or '').strip() for b in body],
                 body[-1].get('to', 0) if body else 0, meta['dur'])
    return '\n\n'.join(paras), dict(source=lan,
                                    **{k: g[k] for k in ('chars', 'cps', 'loop', 'tail', 'qc')})


def fine(meta, speakers, check, solo=False):
    cdir = WORK / meta['bvid']; cdir.mkdir(parents=True, exist_ok=True)
    spans = asr.spans(meta['dur'])
    hot, fix = tables(meta.get('up', ''))
    need = [i for i in range(len(spans)) if not (cdir / f'seg{i}.json').exists()]
    if need:
        log(f"   热词 {len(hot)} 个 · 替换 {len(fix)} 条 · 分 {len(spans)} 段"
            + ('  [单人模式]' if solo else ''))
        with tempfile.TemporaryDirectory() as tmp:
            log('   下载音频…')
            full = fetch.audio(meta, tmp)
            for i in need:
                a, b = spans[i]
                piece = fetch.slice_audio(full, pathlib.Path(tmp) / f's{i}.mp3', a, b - a)
                u = asr.recognize(piece, hot, speaker_info=not solo, log=log)
                (cdir / f'seg{i}.json').write_text(json.dumps(u, ensure_ascii=False),
                                                   encoding='utf-8')
                piece.unlink(missing_ok=True)
        log('   音频已删')
    else:
        log(f'   复用缓存 {len(spans)} 段')
    segs = [json.loads((cdir / f'seg{i}.json').read_text(encoding='utf-8'))
            for i in range(len(spans))]
    rows = merge.combine(segs, spans)
    if solo:
        turns = merge.to_paragraphs(rows, fix)
        text = plain = '\n\n'.join(turns)
        names = {}
    else:
        names = merge.name_speakers(rows, speakers)
        turns = merge.to_turns(rows, names, fix)
        text = '\n\n'.join(f'**{w}**：{t}' for w, t in turns)
        plain = ' '.join(t for _, t in turns)
    g = qc.gates(plain, [r[2] for r in rows], rows[-1][0] if rows else 0, meta['dur'])
    extra = dict(source=f'豆包{asr.RESOURCE} 热词{len(hot)} 替换{len(fix)}', chars=g['chars'],
                 **({'paragraphs': len(turns)} if solo else
                    {'turns': len(turns), 'speakers': ' / '.join(sorted(set(names.values())))}),
                 qc=g['qc'])
    rp = None
    if check:
        log('   双源交叉核验…')
        _, body = fetch.subtitle(meta)
        ref = ''.join(b['content'] for b in body) if body else ''
        div = qc.divergence(ref, plain) if ref else []
        neg = qc.negation_check(ref, plain) if ref else []
        num = qc.number_check(ref, plain) if ref else []
        lone, nw, nu = qc.lone_words(text)
        rp = cdir / '待核清单.md'
        rp.write_text(qc.review_md(meta['title'], lone, nw, nu, div, neg=neg, num=num),
                      encoding='utf-8')
        extra['unresolved'] = len(div) + len(neg) + len(num) + len(lone)
        log(f'   分歧 {len(div)} · 否定词 {len(neg)} · 数字 {len(num)} · 孤词 {len(lone)}'
            f'  → 待核 {extra["unresolved"]} 项')
    return text, extra, rp


GUEST = [r'对话?([\u4e00-\u9fff]{2,4})的', r'和([\u4e00-\u9fff]{2,4})聊',
         r'对话([\u4e00-\u9fff]{2,4})', r'专访([\u4e00-\u9fff]{2,4})']

def guess_guest(title):
    """访谈类节目嘉宾每期不同，但标题里通常就有。"""
    import re as _re
    for pat in GUEST:
        m = _re.search(pat, title or '')
        if m: return m.group(1)
    return None


def run_one(meta, a, quiet=False):
    cfg = ups().get(meta.get('up'), {})
    solo = a.solo or cfg.get('solo', False)
    if a.speakers:
        sp = tuple(a.speakers.split(',', 1))
    elif cfg.get('host'):
        sp = (cfg['host'], guess_guest(meta.get('title')) or '嘉宾')
    else:
        sp = None
    if a.finalize or a.review or a.fine:
        text, extra, rp = fine(meta, sp, not a.no_check, solo=solo)
        if a.finalize:
            import datetime
            extra['verified'] = datetime.date.today().isoformat()
        p = write(meta, text, extra)
    else:
        fp = final_path(meta)
        if fp.exists() and '豆包' in fp.read_text(encoding='utf-8')[:400]:
            log('  ! 已有精修版，快车道不覆盖。要重出用 --review'); return 3, None
        text, extra = fast(meta)
        if text is None:
            log('  ✗ 无中文字幕轨 —— 加 --fine 走豆包'); return 2, None
        p = write(meta, text, extra); rp = None
    log(f"  ✓ {p.relative_to(ROOT)}  ({p.stat().st_size//1024} KB)")
    if a.finalize:
        shutil.rmtree(WORK / meta['bvid'], ignore_errors=True)
        log(f"  ✓ 已删除 .work/{meta['bvid']}/（清单 + 缓存）—— 此后重出需重花额度")
    elif rp and not quiet:
        log(f"  · {rp.relative_to(ROOT)}（过程文件，定稿时会删）")
    return 0, p


def run_batch(kind, name, bvids, a):
    """批量 + 增量：已有文稿的跳过，除非 --all。单条失败不中断。"""
    todo, skip = [], 0
    for bv in bvids:
        try:
            m = fetch.resolve(f'https://www.bilibili.com/video/{bv}/')
        except Exception as e:
            log(f'  ✗ {bv} 解析失败: {e}'); continue
        if not a.all and final_path(m).exists(): skip += 1; continue
        todo.append(m)
    log(f"《{name}》{kind} · 远端 {len(bvids)} 条 · 已有 {skip} 条 · 待处理 {len(todo)} 条")
    if not todo:
        log('  已是最新，无需处理'); return 0
    if a.fine:
        h = sum(m['dur'] for m in todo) / 3600
        log(f"  精修全部：{h:.1f} 小时音频 · 约 {h*0.8:.1f} 元")
        if not a.yes:
            log('  ! 批量精修要花钱，需显式加 --yes 确认'); return 4
    ok = err = 0
    for i, m in enumerate(todo, 1):
        log(f"\n[{i}/{len(todo)}] {m['title'][:40]}  ({m['dur']//60}分)")
        try:
            c, _ = run_one(m, a, quiet=True)
            ok += (c == 0); err += (c != 0)
        except Exception as e:
            log(f'  ✗ {e}'); err += 1
    log(f"\n完成：成功 {ok} · 失败 {err} · 跳过 {skip}")
    return 0 if not err else 5


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('url', nargs='?')
    ap.add_argument('--fine', action='store_true', help='精修：豆包 ASR（付费）')
    ap.add_argument('--fast', action='store_true', help='快车道：平台字幕（免费）')
    ap.add_argument('--no-check', action='store_true', help='精修时跳过双源核对（不建议）')
    ap.add_argument('--review', metavar='BV', help='只用缓存重出，不花额度')
    ap.add_argument('--finalize', metavar='BV', help='定稿：重出最终稿并删除全部过程文件')
    ap.add_argument('--speakers', help='主持人,嘉宾')
    ap.add_argument('--solo', action='store_true', help='单人口播：关闭说话人分离')
    ap.add_argument('--all', action='store_true', help='批量时连已有文稿的也重跑')
    ap.add_argument('--yes', action='store_true', help='确认批量精修的花费')
    a = ap.parse_args()

    target = a.finalize or a.review or a.url
    if not target: ap.print_help(); return 1

    if not (a.review or a.finalize) and target.startswith('http'):
        exp = fetch.expand(target)
        if exp: return run_batch(*exp, a)

    meta = fetch.resolve(target if target.startswith('http')
                         else f'https://www.bilibili.com/video/{target}/')
    log(f"《{meta['title']}》")
    log(f"  {meta.get('up')} · {meta.get('pub')} · {meta['dur']//60}分{meta['dur']%60}秒")

    # 没指定方式时当面问一次，把代价摆出来再选；非交互环境默认走免费快车道
    if not (a.fine or a.fast or a.review or a.finalize):
        d = meta['dur']
        est = f"{d//60+2} 分钟" if d > 3600 else f"{max(4, 5 + d//110)} 秒"
        log('')
        log('  选择方式：')
        log('    1) 快车道   平台字幕 · 约 1 秒 · 免费')
        log('               无标点 · 无说话人 · 已知会整段丢内容')
        log(f'    2) 精修     豆包 ASR · 约 {est} · {d/3600*0.8:.2f} 元')
        log('               带标点和说话人 · 双源交叉核对 · 产出待核清单')
        if sys.stdin.isatty():
            try: c = input('  选 [1]: ').strip() or '1'
            except EOFError: c = '1'
        else:
            c = '1'; log('  （非交互环境，默认 1）')
        if c == '2': a.fine = True
        log('')

    return run_one(meta, a)[0]


if __name__ == '__main__':
    sys.exit(main())
