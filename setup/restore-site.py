#!/usr/bin/env python3
"""把 zhuanxieku.netlify.app 上已发布的文稿还原成 <库>/文稿/*.md，并还原「入库日期」。

新机器上 文稿/ 是空的；不先还原就部署，站上的旧稿会被整站覆盖掉。
站点 HTML 是 md 的确定性渲染（publish.py 的 body_html），所以可逆、逐字一致。
已存在的文件不动。用法：restore-site.py <库根目录>
"""
import sys, re, json, html, pathlib, urllib.request, datetime

SITE = 'https://zhuanxieku.netlify.app'
ROOT = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'src'))
import ts  # 用流水线自己的 final_path，文件名才一致

get = lambda p: urllib.request.urlopen(SITE + p, timeout=30).read().decode('utf-8')
un = html.unescape

index = get('/')
# 首页「最近添加」卡片：链接可能是 /d/bv.html 或 /d/bv（新旧两版生成器都认）
known = dict(re.findall(r"""href=['"]/d/([^'".]+)(?:\.html)?['"]><b>.*?入库 (\d{4}-\d{2}-\d{2})""", index))
bvs = [d['b'] for d in json.loads(get('/search.json'))]

made, ids = 0, {}
for b in bvs:
    page = get(f'/d/{b}.html')
    title = un(re.search(r'<h1>(.*?)</h1>', page, re.S).group(1))
    m = re.search(r'<div class="meta">(.*?) · (.*?) · (.*?) · (.*?) 字(.*?)<br><a href="https://www\.bilibili\.com/video/([^/]+)/">', page, re.S)
    up, pub, dur, chars, tag, BV = (un(x) for x in m.groups())
    ids[b] = BV
    p = ts.final_path({'up': up, 'pub': pub, 'title': title})
    if p.exists():
        continue
    body = page.split('margin:1.2rem 0">', 1)[1].split('</div><div class="wrap"><footer>', 1)[0]
    paras = [f'**{un(x.group(1))}**：{un(x.group(2))}' if x.group(1) is not None else un(x.group(3))
             for x in re.finditer(r'<p class="t"><i>(.*?)</i>(.*?)</p>|<p>(.*?)</p>', body, re.S)]
    fm = {'title': title, 'up': up, 'bvid': BV, 'published': pub, 'duration': dur,
          'source': '快车道（从站点恢复）' if '快车道' in tag else '豆包（从站点恢复）',
          'chars': chars, 'restored': datetime.date.today().isoformat()}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('---\n' + '\n'.join(f'{k}: {v}' for k, v in fm.items() if v not in (None, ''))
                 + '\n---\n\n' + '\n\n'.join(paras) + '\n', encoding='utf-8')
    made += 1

# 入库日期：首页能看到的照抄，其余排在它们之前一天（只影响「最近添加」排序）
aj = ROOT / '.work' / 'added.json'
aj.parent.mkdir(parents=True, exist_ok=True)
cur = json.loads(aj.read_text(encoding='utf-8')) if aj.exists() else {}
floor = ((min(datetime.date.fromisoformat(d) for d in known.values()) - datetime.timedelta(days=1)).isoformat()
         if known else datetime.date.today().isoformat())
for b, BV in ids.items():
    cur.setdefault(BV, known.get(b, floor))
aj.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding='utf-8')
print(f'站上 {len(bvs)} 篇，新还原 {made} 篇')
