#!/usr/bin/env python3
"""把网页备用入口（云端）出的稿收进 文稿/，下次发布就成了正式的静态文稿。

publish.py 构建前会自动调用；也可以单独跑：src/cloud_pull.py
规则同 ts.py：本地已有就不动；唯一的例外是「本地是快车道、云端是精修」，用精修替换。
"""
import os, re, sys, json, time, pathlib, datetime, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ts

SITE = os.environ.get('ZX_SITE', 'https://zhuanxieku.netlify.app')


def _get(path):
    req = urllib.request.Request(SITE + path, headers={'User-Agent': 'transcribe-cloud-pull'})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def pull(root):
    root = pathlib.Path(root)
    have = {}                                   # bvid → (路径, 是否精修)
    for p in (root / '文稿').rglob('*.md'):
        t = p.read_text(encoding='utf-8')[:800]
        m = re.search(r'^bvid: (\S+)', t, re.M)
        if m:
            have[m.group(1)] = (p, '豆包' in t)
    n = 0
    for h in _get(f'/api/cloud?list&_={int(time.time())}').get('docs', []):
        bv = h['bvid']
        old = have.get(bv)
        if old and (old[1] or h['mode'] != 'Y'):
            continue
        d = _get(f'/api/cloud?doc={bv}')
        meta = {'title': d['title'], 'up': d['up'], 'bvid': bv, 'pub': d['pub'], 'dur': int(d['dur'])}
        extra = {k: d.get(k) for k in ('source', 'chars', 'paragraphs', 'turns', 'speakers')}
        extra['cloud'] = datetime.date.fromtimestamp(d['created'] / 1000).isoformat()
        p = ts.write(meta, d['text'], extra)
        if old and old[0] != p:
            old[0].unlink(missing_ok=True)      # 快车道旧稿换了文件名时，删掉旧的免得重复
        n += 1
        print(f'  ☁ 收进云端稿：{p.relative_to(root)}')
    return n


if __name__ == '__main__':
    print(f'收进 {pull(pathlib.Path(__file__).resolve().parent.parent)} 篇')
