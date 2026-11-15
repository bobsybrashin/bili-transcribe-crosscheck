#!/usr/bin/env python3
"""把自己整理好的文稿一步同步到转写库网站——不经过 B站、不转写、不花钱。

  upload.py <文件.md|.txt> [...]       Finder 里选中文件按 ⌃⌘U（或右键 → 快速操作 → 同步到转写库）也是调它

文件格式（都可以省）：
  ---
  title: 标题                 省了就用第一行的「# 标题」或文件名
  up: 作者/讲者               省了记作「整理稿」
  published: 2026-10-07       省了用今天
  url: 原文链接               阅读页的「打开原文」
  source: 来源说明            比如「英文为官方稿，中文为 Claude 翻译」
  note: 一句背景
  ---
  正文，空行分段。中英对照就是英文一段、中文一段交替，网站自动排成对照样式。

一步做完：读文件 → 整理格式（补标题、日期、编号）→ 收进 文稿/ → 放上网站「新稿」区（不发布、不花额度，
下次发布时变成正式文稿）。同一篇（同标题同日期）改完再同步，会覆盖旧版。
结束时弹通知并打开任务页，和热键转写一样：成功写字数，失败写卡在哪一步、原因、怎么办。
"""
import os, re, sys, hashlib, datetime, pathlib, subprocess, traceback
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import task, ts

ROOT = task.ROOT
task.STEPS['U'] = [('read', '读文件'), ('tidy', '整理格式'), ('save', '收进文稿'), ('upload', '放上网站')]
SAFE = re.compile(r'[\\/:*?"<>|\n\r\t]')


def parse(raw, path):
    raw = raw.replace('\r\n', '\n').lstrip('﻿')
    m = re.match(r'---\n(.*?)\n---\n+(.*)', raw, re.S)
    fm, body = ({}, raw) if not m else (
        {k.strip(): v.strip() for k, v in (l.split(':', 1) for l in m.group(1).splitlines() if ':' in l)}, m.group(2))
    paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    if paras and paras[0].startswith('# ') and '\n' not in paras[0]:
        fm.setdefault('title', paras.pop(0)[2:].strip())          # 「# 标题」当标题，不进正文
    # 段内换行：英文接成空格，中文直接接上
    paras = [re.sub(r'\s*\n\s*', ' ' if re.search(r'[A-Za-z]\n[A-Za-z]', p) else '', p) for p in paras]
    return fm, paras


def write(fm, paras):
    title = fm.get('title') or ''
    up = fm.get('up') or '整理稿'
    pub = fm.get('published') or datetime.date.today().isoformat()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', pub):
        raise ValueError(f'published 要写成 2026-10-07 这样，现在是「{pub}」')
    doc_id = fm.get('id') or f"M{pub.replace('-', '')}-{hashlib.sha1(title.encode()).hexdigest()[:6]}"
    text = '\n\n'.join(paras)
    chars = len(re.findall(r'[一-鿿]', text)) + len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text))
    head = {'title': title, 'up': up, 'id': doc_id, 'published': pub, 'url': fm.get('url', ''),
            'source': fm.get('source') or '手动整理', 'note': fm.get('note', ''), 'kind': 'manual',
            'chars': chars, 'synced': datetime.date.today().isoformat()}
    path = ts.final_path({'up': up, 'pub': pub, 'title': title})
    for old in (ROOT / '文稿').rglob('*.md'):                  # 同一篇改了标题、换了文件名：删掉旧的
        if old != path and re.search(rf'^id: {re.escape(doc_id)}$', old.read_text(encoding='utf-8')[:800], re.M):
            old.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('---\n' + '\n'.join(f'{k}: {v}' for k, v in head.items() if v not in (None, ''))
                    + '\n---\n\n' + text + '\n', encoding='utf-8')
    return head, text, path


def one(src):
    T = task.Task('U', str(src))
    task.T = T
    try:
        T.enter('read')
        src = pathlib.Path(src).expanduser()
        T.d['title'] = src.name                    # 失败时任务页上至少看得出是哪个文件
        if not src.exists():
            return T.fail(f'找不到文件：{src}', '找不到这个文件', '在 Finder 里选中文件再按 ⌃⌘U') or T
        if src.suffix.lower() not in ('.md', '.txt', '.markdown'):
            return T.fail(f'不支持的格式：{src.suffix}', f'只支持 .md / .txt，这个是 {src.suffix or "无后缀"}',
                          '另存为纯文本（.txt 或 .md）再同步') or T
        raw = src.read_text(encoding='utf-8')
        T.enter('tidy')
        fm, paras = parse(raw, src)
        fm.setdefault('title', SAFE.sub('', src.stem).strip())
        if not paras:
            return T.fail('正文是空的', '文件里没有正文', '在标题下面空一行，写上正文再同步') or T
        T.d.update(title=fm['title'])
        T.enter('save')
        head, text, path = write(fm, paras)
        T.d.update(bvid=head['id'])
        T.enter('upload')
        try:
            if not T.pw:
                raise RuntimeError('没有云端口令（~/.config/transcribe/cloud-pass）')
            task.post({'action': 'putdoc', 'pass': T.pw, 'doc': {
                'bvid': head['id'], 'title': head['title'], 'up': head['up'], 'pub': head['published'], 'dur': 0,
                'mode': 'M', 'source': head['source'], 'url': head['url'], 'note': head['note'],
                'chars': head['chars'], 'text': text}}, timeout=20)
        except Exception as e:
            s = T.step('upload')
            s.update(s='fail', note=f'没放上网站（{str(e)[:60]}），稿子在本机')
        T.done(outcome='已同步', chars=head['chars'], path=str(path.relative_to(ROOT)),
               note=f'{len(paras)} 段' + ('，中英对照' if {task_lang(p) for p in paras} == {'zh', 'en'} else ''))
    except Exception as e:
        traceback.print_exc()
        T.fail(''.join(traceback.format_exception_only(type(e), e)))
    return T


def task_lang(p):
    cjk = len(re.findall(r'[一-鿿]', p))
    return 'zh' if cjk > 0.3 * max(1, len(re.sub(r'\s', '', p))) else 'en'


if __name__ == '__main__':
    files = sys.argv[1:]
    if not files:
        print(__doc__); sys.exit(1)
    done = [one(f) for f in files]
    ok = [t for t in done if t.d['status'] == 'done']
    last = done[-1].d
    if len(done) == 1:
        if ok:
            up = next((s for s in last['steps'] if s['k'] == 'upload'), {})
            task.notify('✓ 已同步' + (' · 网站上暂时看不到' if up.get('s') == 'fail' else ''),
                        f"《{last.get('title', '')[:40]}》 · {last.get('chars', 0)} 字")
        else:
            bad = next((s['name'] for s in last['steps'] if s['s'] == 'fail'), '')
            task.notify(f'✗ 卡在「{bad}」', f"{last['reason']} → {last['fix']}")
    else:
        task.notify(f'同步完 {len(done)} 篇', f'成功 {len(ok)} 篇，失败 {len(done) - len(ok)} 篇')
    target = f"{task.SITE}/t.html?id={last['id']}" if done[-1].synced else str(task.local_page(last))
    if not os.environ.get('ZX_QUIET'):
        subprocess.run(['open', target], capture_output=True)
    print(f'  任务页：{target}')
    sys.exit(0 if len(ok) == len(done) else 1)
