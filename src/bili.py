#!/usr/bin/env python3
"""B站接口共用层：WBI 签名、请求、字幕抓取、合并成段、质检"""
import os, json, time, hashlib, urllib.parse, urllib.request, functools, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
COOKIE_PATH = pathlib.Path(os.environ.get('BILI_COOKIE_JSON')
                           or pathlib.Path.home() / '.config/transcribe/bilibili-cookie.json')
HDR = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                     'Chrome/120 Safari/537.36',
       'Referer': 'https://www.bilibili.com/'}

FIELDS = ('sessdata', 'bili_jct', 'dede_user_id')

@functools.lru_cache(1)
def cookie():
    """登录态。未登录时字幕接口返回空轨，所以这一步不是可选的。
    懒加载：没有 cookie 也能 import 本模块，qc/merge 才能单独用。"""
    if not COOKIE_PATH.exists():
        raise RuntimeError(
            f'找不到 B站 cookie 文件：{COOKIE_PATH}\n'
            f'  换路径用环境变量 BILI_COOKIE_JSON。文件内容是三个键的 JSON：\n'
            f'  {{"sessdata": "…", "bili_jct": "…", "dede_user_id": "…"}}\n'
            f'  浏览器登录 bilibili.com 后，从 Cookie 里分别取 '
            f'SESSDATA / bili_jct / DedeUserID 三项的值填进去。')
    try:
        ck = json.loads(COOKIE_PATH.read_text(encoding='utf-8'))
    except Exception as e:
        raise RuntimeError(f'{COOKIE_PATH} 不是合法 JSON：{e}')
    miss = [k for k in FIELDS if not ck.get(k)]
    if miss:
        raise RuntimeError(f'{COOKIE_PATH} 缺少字段 {miss}，需要 {list(FIELDS)}')
    return '; '.join(f'{n}={ck[k]}' for n, k in
                     zip(('SESSDATA', 'bili_jct', 'DedeUserID'), FIELDS))

def headers():
    return {**HDR, 'Cookie': cookie()}

MIX = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,
       37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]

def get(u, tries=3, raw=False):
    last = None
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers=headers()), timeout=30)
            b = r.read()
            return b if raw else json.loads(b)
        except Exception as e:
            last = e; time.sleep(1.5 * (i + 1))
    raise last

@functools.lru_cache(1)
def mixin_key():
    n = get('https://api.bilibili.com/x/web-interface/nav')['data']['wbi_img']
    raw = n['img_url'].rsplit('/',1)[-1].split('.')[0] + n['sub_url'].rsplit('/',1)[-1].split('.')[0]
    return ''.join(raw[i] for i in MIX)[:32]

def wbi(p):
    p = dict(p); p['wts'] = int(time.time())
    q = urllib.parse.urlencode(sorted(p.items()))
    p['w_rid'] = hashlib.md5((q + mixin_key()).encode()).hexdigest()
    return urllib.parse.urlencode(sorted(p.items()))

def secs(s):
    p = [int(x) for x in str(s).split(':')]
    return p[0]*3600+p[1]*60+p[2] if len(p) == 3 else (p[0]*60+p[1] if len(p) == 2 else p[0])

# ── 投稿清单 ──────────────────────────────────────────────────
def list_videos(mid):
    out, pn = [], 1
    while True:
        d = get('https://api.bilibili.com/x/space/wbi/arc/search?' +
                wbi({'mid': mid, 'ps': 50, 'pn': pn, 'order': 'pubdate', 'platform': 'web'}))
        if d.get('code') != 0: raise RuntimeError(f"space {d.get('code')} {d.get('message')}")
        vl = d['data']['list']['vlist']; total = d['data']['page']['count']
        out += vl
        if len(out) >= total or not vl: break
        pn += 1; time.sleep(0.4)
    return out

# ── 字幕 ──────────────────────────────────────────────────────
def cid_of(bvid):
    d = get(f'https://api.bilibili.com/x/player/pagelist?bvid={bvid}')
    return d['data'][0]['cid'] if d.get('code') == 0 and d.get('data') else None

def sub_tracks(aid, cid):
    d = get('https://api.bilibili.com/x/player/wbi/v2?' + wbi({'aid': aid, 'cid': cid}))
    if d.get('code') != 0: return []
    return ((d.get('data') or {}).get('subtitle') or {}).get('subtitles') or []

PREF = ['zh-CN', 'zh-Hans', 'zh', 'ai-zh']          # 官方 CC 优先于 AI 字幕
def pick(tracks):
    """只认中文轨。只有 ai-en/ai-ja 等译轨时返回 None → 转 whisper，绝不落译文。"""
    for lan in PREF:
        for t in tracks:
            if t.get('lan') == lan: return t
    for t in tracks:                                 # 兜底：任何 zh 开头的变体
        if str(t.get('lan', '')).lower().startswith(('zh', 'ai-zh')): return t
    return None

TAG = re.compile(r'<[^>]{1,20}>')
def fetch_sub(track):
    u = track['subtitle_url']
    if u.startswith('//'): u = 'https:' + u
    body = get(u).get('body') or []
    for b in body:                                   # 官方 CC 带 <b> 标签，剥掉
        if b.get('content'): b['content'] = TAG.sub('', b['content']).strip()
    return body

# ── 合并成段：只连接，不改字 ───────────────────────────────────
def paragraphs(body, gap=1.2, maxlen=320):
    paras, cur, prev_end = [], [], None
    for it in body:
        c = (it.get('content') or '').strip()
        if not c: continue
        f, t = it.get('from', 0), it.get('to', 0)
        brk = (prev_end is not None and f - prev_end > gap) or sum(len(x) for x in cur) > maxlen
        if brk and cur:
            paras.append(' '.join(cur)); cur = []
        cur.append(c); prev_end = t
    if cur: paras.append(' '.join(cur))
    return paras

# ── 质检 ──────────────────────────────────────────────────────
def loop_ratio(lines, look=6):
    if len(lines) < 10: return 0.0
    dup = sum(1 for i, l in enumerate(lines) if l and l in lines[max(0, i-look):i])
    return round(dup / len(lines), 3)

def qc(paras, body, dur):
    text = ''.join(paras).replace(' ', '')
    chars = len(text)
    cps = round(chars / dur, 3) if dur else 0
    lr = loop_ratio([(b.get('content') or '').strip() for b in body])
    tail = round((body[-1].get('to', 0) / dur), 3) if body and dur else 0
    bad = []
    if chars < 200: bad.append('过短')
    if cps < 1.5: bad.append(f'密度低{cps}')
    if lr > 0.25: bad.append(f'循环{lr}')
    if tail < 0.90: bad.append(f'尾部截断{tail}')
    return {'chars': chars, 'cps': cps, 'loop': lr, 'tail': tail,
            'qc': 'pass' if not bad else 'warn', 'bad': bad}

SAFE = re.compile(r'[\\/:*?"<>|\n\r\t]')
def safe_name(s, n=44):
    return SAFE.sub('', (s or '').strip())[:n].rstrip(' .')
