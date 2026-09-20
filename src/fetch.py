#!/usr/bin/env python3
"""取源层：把任意链接解析成 meta，并提供「字幕」和「音频」两种取法。
换视频来源只改这个文件。"""
import os, re, time, subprocess, pathlib, urllib.request
import bili

XOR, MASK, BASE = 23442827791579, 2251799813685247, 58
TBL = 'FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf'

def bv2av(bv):
    a = list(bv); a[3], a[9] = a[9], a[3]; a[4], a[7] = a[7], a[4]
    n = 0
    for c in a[3:]: n = n * BASE + TBL.index(c)
    return (n & MASK) ^ XOR

def _unshort(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=bili.HDR), timeout=15)
        return r.geturl()
    except Exception:
        return url

def expand(url):
    """把批量链接摊开成 bvid 列表。单视频返回 None（交给 resolve）。
    → (kind, name, [bvid...]) 或 None
    顺序要紧：合集链接里也含 space.bilibili.com/<mid>，必须先判合集。"""
    u = url.strip()
    if 'b23.tv' in u: u = _unshort(u)
    mm = re.search(r'space\.bilibili\.com/(\d+)|[?&]mid=(\d+)', u)
    mid = int(mm.group(1) or mm.group(2)) if mm else None

    # 1) 合集 / 系列
    sm = re.search(r'/lists/(\d+)|[?&]sid=(\d+)|season_id=(\d+)|series_id=(\d+)', u)
    if sm and mid:
        sid = int(next(g for g in sm.groups() if g))
        series = 'series' in u
        out, pn, name = [], 1, f'合集{sid}'
        while True:
            if series:
                api = ('https://api.bilibili.com/x/series/archives'
                       f'?mid={mid}&series_id={sid}&only_normal=true&pn={pn}&ps=100')
            else:
                api = ('https://api.bilibili.com/x/polymer/web-space/seasons_archives_list'
                       f'?mid={mid}&season_id={sid}&sort_reverse=false'
                       f'&page_num={pn}&page_size=100')
            d = bili.get(api)
            if d.get('code') != 0: break
            data = d.get('data') or {}
            ar = data.get('archives') or []
            name = (data.get('meta') or {}).get('name') or name
            out += [a['bvid'] for a in ar]
            total = ((data.get('page') or {}).get('total')
                     or (data.get('meta') or {}).get('total') or len(out))
            if len(out) >= total or not ar: break
            pn += 1; time.sleep(0.4)
        if out: return ('合集', name, out)

    # 2) UP主空间全部投稿
    if mid and '/lists/' not in u and 'sid=' not in u:
        vs = bili.list_videos(mid)
        return ('UP主', (vs[0].get('author') if vs else str(mid)), [v['bvid'] for v in vs])
    return None

def _from_ep(u):
    """番剧 ep/ss → bvid"""
    m = re.search(r'/(ep|ss)(\d+)', u)
    if not m: return None
    k, i = m.group(1), m.group(2)
    api = (f'https://api.bilibili.com/pgc/view/web/season?ep_id={i}' if k == 'ep'
           else f'https://api.bilibili.com/pgc/view/web/season?season_id={i}')
    d = bili.get(api)
    if d.get('code') != 0: return None
    eps = (d.get('result') or {}).get('episodes') or []
    if k == 'ep':
        for e in eps:
            if str(e.get('id')) == i: return e.get('bvid')
    return eps[0].get('bvid') if eps else None

def resolve(url):
    """→ {'site','bvid','aid','cid','title','up','dur','pub','url'}；无法识别抛异常"""
    u = url.strip()
    if 'b23.tv' in u: u = _unshort(u)
    if re.search(r'youtube\.com|youtu\.be', u):
        raise NotImplementedError('YouTube 取源尚未接入（fetch.py 里加一个分支即可）')
    if re.search(r'weixin|channels|视频号', u):
        raise NotImplementedError('微信视频号无公开接口，需单独攻关')
    m = re.search(r'(BV[0-9A-Za-z]{10})', u)
    bvid = m.group(1) if m else _from_ep(u)
    if not bvid: raise ValueError(f'无法从链接中识别 BV 号: {url}')
    aid = bv2av(bvid)
    d = bili.get(f'https://api.bilibili.com/x/player/pagelist?bvid={bvid}')
    if d.get('code') != 0: raise RuntimeError(f"pagelist {d.get('code')} {d.get('message')}")
    p = d['data'][0]
    meta = {'site': 'bilibili', 'bvid': bvid, 'aid': aid, 'cid': p['cid'],
            'title': p.get('part') or bvid, 'dur': p['duration'], 'up': '未知', 'pub': '',
            'url': f'https://www.bilibili.com/video/{bvid}/'}
    try:                                    # view 补 UP主/标题/发布日；本机可用
        v = bili.get(f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}')
        if v.get('code') == 0:
            import datetime
            vd = v['data']
            meta['title'] = vd.get('title') or meta['title']
            meta['up'] = (vd.get('owner') or {}).get('name') or '未知'
            meta['pub'] = datetime.datetime.fromtimestamp(vd.get('pubdate', 0)).strftime('%Y-%m-%d')
    except Exception:
        pass
    return meta

def subtitle(meta):
    """快车道：平台自带字幕。→ (lan, body[]) 或 (None, [])"""
    tr = bili.pick(bili.sub_tracks(meta['aid'], meta['cid']))
    return (tr['lan'], bili.fetch_sub(tr)) if tr else (None, [])

# yt-dlp 默认借用浏览器的登录态下高码率音频。这会去读你本机的 cookie 库
# （macOS 上还会弹钥匙串授权）。设 YTDLP_COOKIES_FROM_BROWSER='' 可完全关掉，
# 代价是只能下到游客可见的码率。
COOKIES_FROM = os.environ.get('YTDLP_COOKIES_FROM_BROWSER', 'chrome')

def audio(meta, workdir, start=None, dur=None):
    """慢车道：下载音频并压成 16k 单声道 mp3。调用方负责删除。→ Path"""
    w = pathlib.Path(workdir); w.mkdir(parents=True, exist_ok=True)
    raw = w / 'src.m4a'
    cmd = ['yt-dlp', '-q', '--no-update',
           *(['--cookies-from-browser', COOKIES_FROM] if COOKIES_FROM else []),
           '-f', 'bestaudio', '-o', str(w / 'src.%(ext)s')]
    if start is not None: cmd += ['--download-sections', f'*{start}-{start + (dur or 600)}']
    subprocess.run(cmd + [meta['url']], check=True)
    if not raw.exists():
        cand = [p for p in w.glob('src.*') if p.suffix != '.mp3']
        if not cand: raise RuntimeError('音频下载失败')
        raw = cand[0]
    out = w / 'a16k.mp3'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', str(raw),
                    '-ar', '16000', '-ac', '1', '-b:a', '24k', str(out), '-y'], check=True)
    raw.unlink(missing_ok=True)
    return out

def slice_audio(src, out, start, dur):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-ss', str(start), '-t', str(dur),
                    '-i', str(src), '-c', 'copy', str(out), '-y'], check=True)
    return out
