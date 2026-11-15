#!/usr/bin/env python3
"""把 文稿/ 生成静态站。**默认只构建，不部署。**

  src/publish.py           只生成 site/
  src/publish.py --serve   生成 + 本地起服务，改完在本地看，不占部署额度
  src/publish.py --deploy  生成 + 推到 Netlify ← 只在改完之后做这一次

发布是有额度的，不是免费动作。本地能验的就别推上去——
实测一天推了 19 次就把 Netlify 免费额度烧穿，站点当天无法更新。
默认值因此反过来：要部署必须显式说。

三个页面：
  index.html  首页   最近添加 · 我的收藏 · 按 UP 主入口
  all.html    全部   搜索 + UP主/时间/质量 三个筛选器，按月分组
  help.html   说明

阅读页 d/<bv>.html 是完整静态 HTML，关掉 JS 也能读；搜索和权重才需要 JS。
权重（收藏）走 /api/w，数据在 Netlify Blobs，跨设备一致。
"""
import os, sys, re, json, html, shutil, pathlib, subprocess, argparse, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS, SITE = ROOT / '文稿', ROOT / 'site'
ADDED = ROOT / '.work' / 'added.json'      # 首次入库日期，站点重建也不丢

# ── 权重参数 ────────────────────────────────────────────────────
# 权重 0.0–1.0，以 0.1 为步长（n = 0..10）。点一次 +0.1，上限 1.0。
# 衰减「两端粘、中间快」：1.0 和 0.2 各要 15 天才降一档，其余档位 3 天。
# 1.0 是「明确要留」，0.2 是「刚够收藏」——两个已决定的状态，不该轻易掉。
FAV_N = 2                       # n ≥ 2 即 权重 ≥ 0.2 进「我的收藏」
HOLD_SLOW = [10, 2]             # 从这些档位下降需要 15 天
DAYS_SLOW, DAYS_FAST = 15, 3
OPENS_PER_STEP = 2              # 打开 2 次 +0.1

CSS = """
:root{--bg:#fbfaf8;--fg:#23201c;--dim:#8a8378;--line:#e6e1d8;--card:#fff;--accent:#7a5c3e;
 --star:#d9a441;--chip:#f2eee6}
@media(prefers-color-scheme:dark){:root{--bg:#16150f;--fg:#e8e4dc;--dim:#918a7e;--line:#2e2a22;
 --card:#1e1c16;--accent:#c9a87c;--star:#e0b45a;--chip:#26231c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:17px/1.85 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",sans-serif;
 -webkit-text-size-adjust:100%}
.wrap{max-width:44rem;margin:0 auto;padding:0 1.1rem 5rem}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
 padding:.75rem 0;margin-bottom:1.2rem;z-index:9}
header .wrap{padding-bottom:0;display:flex;align-items:center;gap:.9rem}
header .sp{margin-left:auto}
header a,header b{font-size:.92rem}
a{color:var(--accent);text-decoration:none}
h1{font-size:1.3rem;line-height:1.5;margin:.2rem 0 .3rem}
h2{font-size:1rem;margin:2rem 0 .6rem;font-weight:600}
h2 .n{color:var(--dim);font-weight:400;font-size:.82rem;margin-left:.4rem}
h3{font-size:.94rem;margin:1.5rem 0 .4rem;font-weight:600;color:var(--fg)}
.meta{color:var(--dim);font-size:.82rem;line-height:1.7}
.sec{font-size:.78rem;color:var(--dim);margin:1.7rem 0 .5rem;
 border-bottom:1px solid var(--line);padding-bottom:.3rem}
.card{display:block;background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:.8rem .9rem;margin-bottom:.5rem;color:inherit;position:relative}
.card b{font-weight:600;font-size:.96rem;line-height:1.5;display:block;margin-bottom:.22rem}
input,select{padding:.6rem .8rem;font-size:.95rem;border:1px solid var(--line);
 border-radius:9px;background:var(--card);color:var(--fg)}
input{width:100%;margin:.2rem 0 .6rem;font-size:1rem}
.bar{display:flex;gap:.45rem;flex-wrap:wrap;margin-bottom:.9rem}
.bar select{flex:1;min-width:6.5rem;font-size:.85rem;padding:.45rem .5rem}
p{margin:0 0 1.1rem;word-break:break-word}
p.t{padding-left:.85rem;border-left:2px solid var(--line)}
p.t i{font-style:normal;font-weight:600;color:var(--accent);display:block;font-size:.85rem;
 margin-bottom:.2rem}
mark{background:#f5d67a;color:#23201c;border-radius:2px}
.hit{font-size:.87rem;color:var(--dim);margin:.28rem 0 .85rem;line-height:1.7}
.tag{display:inline-block;font-size:.71rem;color:var(--dim);background:var(--chip);
 border-radius:4px;padding:.05rem .38rem;margin-left:.3rem}
.foot{display:flex;align-items:center;gap:.5rem;margin-top:.5rem}
.wt{display:flex;align-items:center;gap:.3rem;flex:none}
.star{font-size:1.05rem;color:var(--line);cursor:pointer;user-select:none;line-height:1;
 padding:.15rem}
.star.on{color:var(--star)}
.num{font-size:.74rem;color:var(--dim);font-variant-numeric:tabular-nums;min-width:1.6rem;
 text-align:right}
.num.on{color:var(--star)}
.stp{display:inline-flex;align-items:center;gap:.1rem;margin-left:.15rem}
.stp button{width:1.35rem;height:1.35rem;line-height:1;padding:0;font-size:.9rem;
 border:1px solid var(--line);border-radius:5px;background:var(--card);color:var(--dim);
 cursor:pointer}
.stp button:active{background:var(--chip)}
.wbar{height:2px;background:var(--line);border-radius:2px;overflow:hidden;flex:1;min-width:2rem}
.wbar i{display:block;height:100%;background:var(--star);width:0}
.rstar{font-size:1.3rem;color:var(--line);cursor:pointer;user-select:none;line-height:1}
.rstar.on{color:var(--star)}
footer{color:var(--dim);font-size:.78rem;margin-top:3rem;border-top:1px solid var(--line);
 padding-top:1rem}
.empty{color:var(--dim);font-size:.87rem;padding:.6rem 0}
code{background:var(--chip);border-radius:4px;padding:.05rem .3rem;font-size:.85em}
kbd{display:inline-block;background:var(--chip);border:1px solid var(--line);border-bottom-width:2px;
 border-radius:5px;padding:.08rem .38rem;font-size:.82em;font-family:inherit;color:var(--fg);
 white-space:nowrap}
table{width:100%;border-collapse:collapse;font-size:.88rem;margin:0 0 1.2rem}
th,td{text-align:left;padding:.45rem .5rem;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:500;font-size:.8rem}
td:first-child,th:first-child{white-space:nowrap;color:var(--dim);width:1%}
.cb{flex:1;padding:.55rem .6rem;font-size:.95rem;border:1px solid var(--line);border-radius:9px;
 background:var(--card);color:var(--fg);cursor:pointer}
.cb:disabled{opacity:.45;cursor:default}
"""

WJS = """
const FAVN=%(favn)d, SLOW=%(slow)s, DS=%(ds)d, DF=%(df)d, OPS=%(ops)d, DAY=864e5;
const LK='transcribe-w', KEY='%(key)s';
const OLD=[0,3,6,8,9,9,10,10,10];          // 旧台阶制数据迁移用
let W={};
const nOf=o=>Math.max(0,Math.min(10,o&&o.n!=null?o.n:(o&&o.s!=null?OLD[Math.min(o.s,8)]:0)));
const wOf=o=>nOf(o)/10;
const fmt=o=>(nOf(o)/10).toFixed(1);
const holdDays=n=>SLOW.includes(n)?DS:DF;
function decay(o){let n=nOf(o),t=o.t||Date.now();
 for(let i=0;i<40&&n>0;i++){const need=holdDays(n)*DAY;
  if(Date.now()-t<need)break; n--; t+=need;}
 o.n=n;o.t=t;delete o.s;return o;}
function lload(){try{W=JSON.parse(localStorage.getItem(LK)||'{}')}catch{W={}}
 for(const k in W)decay(W[k]);}
function lsave(){try{localStorage.setItem(LK,JSON.stringify(W))}catch{}}
async function pull(){try{const r=await fetch('/api/w?_='+Date.now());const d=await r.json();
 if(d&&d.w)for(const k in d.w){const sv=d.w[k],lo=W[k];
  if(!lo||(sv.t||0)>=(lo.t||0))W[k]=sv;}}catch{}
 for(const k in W)decay(W[k]);lsave();}
let tm=null;
function push(){if(!KEY)return;clearTimeout(tm);tm=setTimeout(async()=>{
 try{await fetch('/api/w',{method:'POST',
  headers:{'content-type':'application/json','x-key':KEY},
  body:JSON.stringify({w:W})});}catch{}},700);}
function setN(bv,n){const o=W[bv]||(W[bv]={n:0,o:0,t:Date.now()});
 o.n=Math.max(0,Math.min(10,n));o.t=Date.now();lsave();push();return o.n;}
function bump(bv,d){const o=W[bv]||(W[bv]={n:0,o:0,t:Date.now()});decay(o);
 return setN(bv,nOf(o)+d);}
function open1(bv){const o=W[bv]||(W[bv]={n:0,o:0,t:Date.now()});decay(o);
 o.o=(o.o||0)+1;if(o.o%%OPS===0)o.n=Math.min(10,nOf(o)+1);
 o.t=Date.now();lsave();push();}
"""


E = lambda s: html.escape(s or '')


def parse(p):
    t = p.read_text(encoding='utf-8')
    m = re.match(r'---\n(.*?)\n---\n+(.*)', t, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ': ' in line:
            k, v = line.split(': ', 1)
            fm[k.strip()] = v.strip()
    return fm, m.group(2).strip()


def added_map(bvs):
    """首次入库日期。站点重建不丢，所以「最近添加」才有意义。"""
    ADDED.parent.mkdir(parents=True, exist_ok=True)
    d = json.loads(ADDED.read_text(encoding='utf-8')) if ADDED.exists() else {}
    today = datetime.date.today().isoformat()
    for b in bvs:
        d.setdefault(b, today)
    for b in [k for k in d if k not in bvs]:
        d.pop(b)
    ADDED.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    return d


def body_html(text):
    out = []
    for para in text.split('\n\n'):
        para = para.strip()
        if not para:
            continue
        sp = re.match(r'\*\*(.+?)\*\*：(.*)', para, re.S)
        out.append(f'<p class="t"><i>{E(sp.group(1))}</i>{E(sp.group(2))}</p>' if sp
                   else f'<p>{E(para)}</p>')
    return '\n'.join(out)


def shell(title, inner, nav, script=''):
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow">'
            f'<title>{E(title)}</title><style>{CSS}</style></head><body>'
            f'<header><div class="wrap">{nav}</div></header>'
            f'<div class="wrap">{inner}</div>'
            f'<div class="wrap"><footer>转写库 · {datetime.datetime.now():%Y-%m-%d %H:%M}'
            f'</footer></div>{script}</body></html>')


def nav(here=''):
    def it(href, label):
        return f'<b>{label}</b>' if href == here else f'<a href="/{href}">{label}</a>'
    return (it('', '首页') + ' · ' + it('all.html', '全部')
            + '<span class="sp"></span>' + it('help.html', '说明'))


def card(d, sub=''):
    fine = '豆包' in d['src']
    tag = '' if fine else '<span class="tag">快车道</span>'
    bv = d['bv'].lower()
    return (f'<div class="card"><a href="/d/{bv}.html"><b>{E(d["title"])}</b>'
            f'<span class="meta">{E(d["up"])} · {E(d["pub"])} · {E(d["dur"])} · '
            f'{E(d["chars"])} 字{tag}{sub}</span></a>'
            f'<div class="foot"><span class="wbar"><i data-w="{bv}"></i></span>'
            f'<span class="wt"><span class="num" data-n="{bv}"></span>'
            f'<span class="star" data-bv="{bv}">★</span></span></div></div>')


HELP = """<h1>说明</h1>
<div class="meta">仓库：<a href="https://github.com/bobsybrashin/bili-transcribe-crosscheck">github.com/bobsybrashin/bili-transcribe-crosscheck</a></div>

<h2>0 · 一步到位</h2>
<p>设计思路：<b>人只做机器做不了的事，其余全交给脚本。</b>机器做不了的只有三样——给出仓库地址、点授权、填 API Key。所以整套东西只有两步，第二步就是验收。</p>
<table>
<tr><th></th><th>你做什么</th><th>脚本做什么</th></tr>
<tr><td>第 1 步</td><td>在 Mac 终端粘贴一行（仓库 README 第一段就是）：<br><code>zsh -c "$(curl -fsSL https://raw.githubusercontent.com/bobsybrashin/bili-transcribe-crosscheck/main/install.sh)"</code><br>答 3 个问题：① 仓库地址 ② 授权（Netlify 授权页点 Authorize、钥匙串点「始终允许」）③ 豆包 API Key</td><td>装工具、拉仓库、还原站上已有文稿、取 B站 登录态、对好站点密钥、放好云端密钥、绑快捷键，最后真跑一遍 T、Y 两条链路自检</td></tr>
<tr><td>第 2 步</td><td>复制 B站 链接，按 <kbd>⌃⌘T</kbd> 免费 或 <kbd>⌃⌘Y</kbd> 精修</td><td>出稿、弹通知</td></tr>
<tr><td>备用</td><td>热键不灵、授权出问题、或不在 Mac 前：首页「云端转写」框粘贴链接，点 T 或 Y</td><td>直接在 Netlify 上转；稿子先进首页「云端新稿」，Mac 下次发布时收进正式文稿</td></tr>
</table>
<p>脚本可以反复跑：哪里坏了就整条重跑，做过的步骤自动跳过。B站 登录约一个月过期，过期时跑 <code>~/Documents/转写库/setup/refresh-cookie.sh</code>，云端会跟着更新。云端口令装机时生成，每台设备第一次用时输一次。</p>

<h3>限制条件（当下不解决，直接写成前提）</h3>
<table>
<tr><td>1</td><td>只支持 macOS；装 Homebrew 时要输开机密码</td></tr>
<tr><td>2</td><td>Chrome 里要已登录 bilibili.com（登录态约一个月过期，跑 refresh-cookie.sh 续）</td></tr>
<tr><td>3</td><td>Netlify 账号要拥有 zhuanxieku 站点</td></tr>
<tr><td>4</td><td>豆包语音要开通「录音文件识别 2.0」，API Key 用新版控制台的</td></tr>
<tr><td>5</td><td>过程中要人点：Netlify 授权、钥匙串「始终允许」、首次通知权限</td></tr>
<tr><td>6</td><td>热键在 Electron 类应用（如 Claude 桌面版）里不生效，在 Chrome、访达里按</td></tr>
<tr><td>7</td><td>免费路线要视频自带中文字幕</td></tr>
<tr><td>8</td><td>云端精修单条 ≤ 2 小时，没有热词表和双源核对</td></tr>
<tr><td>9</td><td>Netlify 免费额度 300/月硬上限，每次部署 15；出稿不花，发布才花</td></tr>
</table>

<h2>1 · 两条出稿路线</h2>
<table>
<tr><th></th><th>快车道</th><th>精修</th></tr>
<tr><td>来源</td><td>B站 AI 字幕</td><td>豆包录音文件识别 2.0</td></tr>
<tr><td>耗时</td><td>约 1 秒</td><td>约 12 秒 / 半小时音频</td></tr>
<tr><td>花费</td><td>免费</td><td>约 0.8 元/小时</td></tr>
<tr><td>标点</td><td>无</td><td>有</td></tr>
<tr><td>说话人</td><td>无</td><td>有</td></tr>
<tr><td>热词表·替换表</td><td>无</td><td>有</td></tr>
<tr><td>双源交叉核对</td><td>未做</td><td>已做</td></tr>
<tr><td>已知缺陷</td><td>会整段丢内容，实测样本约 3.7%，偏向人名</td><td>—</td></tr>
</table>
<p>列表里标着「快车道」的就是前者，<b>没标的都是精修稿</b>——随便读，不用自己判断成色。</p>

<h2>2 · 收藏怎么算</h2>
<table>
<tr><th>动作</th><th>权重变化</th></tr>
<tr><td>点一次 ★</td><td>+0.1（上限 1.0）</td></tr>
<tr><td>打开阅读页 2 次</td><td>+0.1</td></tr>
<tr><td>「全部」页按 − / ＋</td><td>手动加减 0.1</td></tr>
<tr><td>闲置：1.0 → 0.9</td><td>−0.1 要 <b>15 天</b></td></tr>
<tr><td>闲置：0.9 → 0.3</td><td>每档 −0.1 要 3 天</td></tr>
<tr><td>闲置：0.2 → 0.1</td><td>−0.1 要 <b>15 天</b></td></tr>
<tr><td>闲置：0.1 → 0.0</td><td>−0.1 要 3 天</td></tr>
</table>
<p>权重 <b>≥ 0.2 进「我的收藏」</b>；两端粘中间快，所以手滑点一次 3 天自己消失，顶格的要 36 天才掉出去——<b>不用手动取消收藏</b>。</p>

<h2>3 · 其他</h2>

<h3>怎么加新稿子</h3>
<p>在 Mac 上<b>复制视频链接 → 按 <kbd>⌃⌘T</kbd> / <kbd>⌃⌘Y</kbd></b>，出稿后弹通知。不在 Mac 前就用首页「云端转写」，手机也能用。</p>
<p>云端精修没有热词表、也不做双源核对，标「云端精修·未核」；要紧的稿子还是回 Mac 走精修。</p>
<p><b>新 UP 主的第一条别直接走精修</b>——热词表在识别那一刻生效，没有表等于白花钱。先配好 <code>tables/hot/&lt;UP主&gt;.json</code> 再跑。</p>

<h3>精修也不是没有错</h3>
<p>交叉核对能抓两套系统<b>不一致</b>的地方，抓不到<b>两套同时错</b>的——两边把同一个人名听成同一个错字时，比对结果是「一致」。所以「已核」是指该做的都做了，不是保证零错。正文里保留了原视频 ID，随时能回去对照。</p>

<h3>收藏存在哪</h3>
<p>{SYNC}</p>

<h3>阅读页不依赖 JS</h3>
<p>正文是完整静态 HTML，关掉 JavaScript 照样能读。只有搜索和收藏需要 JS。</p>
"""

SYNC_RW = ('存 Netlify Blobs，跨设备一致，本机浏览器留一份缓存所以离线也能看到上次的状态。'
           '写入密钥在构建时烤进页面，<b>不会弹窗问你要</b>。')
SYNC_RO = ('构建时没有设 <code>SITE_WRITE_KEY</code>，所以这是个<b>只读站点</b>：'
           '能读到服务端已有的权重，你点的星只留在本机浏览器里，不会写回去、也不跨设备。'
           '要开写入，设好环境变量再构建一次。')


def build():
    try:                                    # 网页备用入口（云端）出的稿，先收进 文稿/ 再构建
        import cloud_pull
        cloud_pull.pull(ROOT)
    except Exception as e:
        print(f'  · 云端文稿没拉到（不影响构建）：{str(e)[:80]}')
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / 'd').mkdir(parents=True)
    docs = []
    for p in sorted(DOCS.rglob('*.md')):
        r = parse(p)
        if not r:
            continue
        fm, text = r
        docs.append({'bv': fm.get('bvid') or p.stem, 'title': fm.get('title', p.stem),
                     'up': fm.get('up', '未知'), 'pub': fm.get('published', ''),
                     'dur': fm.get('duration', ''), 'chars': fm.get('chars', ''),
                     'src': fm.get('source', ''), 'unresolved': fm.get('unresolved', ''),
                     'text': text})
    add = added_map([d['bv'] for d in docs])
    for d in docs:
        d['add'] = add.get(d['bv'], '')

    # 写入密钥烤进页面：换来零弹窗。挡得住偶然撞见网址的人，挡不住翻源码的人——
    # 对「我收藏了哪几篇稿子」这种数据，这个取舍是合理的；别往里放更敏感的东西。
    # 没设 SITE_WRITE_KEY 就生成只读站：权重能读能显示，改动只留在本机 localStorage。
    key = os.environ.get('SITE_WRITE_KEY', '').strip()
    wjs = WJS % {'favn': FAV_N, 'slow': json.dumps(HOLD_SLOW), 'ds': DAYS_SLOW,
                 'df': DAYS_FAST, 'ops': OPENS_PER_STEP, 'key': key}

    # ── 阅读页 ──
    for d in docs:
        fine = '豆包' in d['src']
        tag = '' if fine else '<span class="tag">快车道·可能有缺失</span>'
        head = (f'<h1>{E(d["title"])}</h1><div class="meta">{E(d["up"])} · {E(d["pub"])}'
                f' · {E(d["dur"])} · {E(d["chars"])} 字{tag}<br>'
                f'<a href="https://www.bilibili.com/video/{d["bv"]}/">在 B站 打开原视频</a>'
                f'</div><hr style="border:0;border-top:1px solid var(--line);margin:1.2rem 0">')
        n = ('<a href="/">首页</a> · <a href="/all.html">全部</a><span class="sp"></span>'
             f'<span class="num rnum"></span>'
             f'<span class="rstar" data-bv="{d["bv"].lower()}">★</span>')
        js = (f'<script>{wjs}\nlload();const BV="{d["bv"].lower()}";'
              'const el=document.querySelector(".rstar");'
              'const nm=document.querySelector(".rnum");'
              'function paint(){const o=W[BV]||{};const n=nOf(o);'
              'el.classList.toggle("on",n>=FAVN);nm.textContent=n?fmt(o):"";'
              'nm.className="rnum"+(n>=FAVN?" on":"");}'
              'paint();open1(BV);pull().then(paint);'
              'el.onclick=()=>{bump(BV,1);paint();};</script>')
        (SITE / 'd' / f'{d["bv"].lower()}.html').write_text(
            shell(d['title'], head + body_html(d['text']), n, js), encoding='utf-8')

    # ── 首页 ──
    recent = sorted(docs, key=lambda d: (d['add'], d['pub']), reverse=True)[:5]
    ups = {}
    for d in docs:
        ups.setdefault(d['up'], []).append(d)
    uplist = ''.join(
        f'<a class="card" href="/all.html#up={E(u)}"><b>{E(u)}</b>'
        f'<span class="meta">{len(v)} 篇 · {sum(int(x["chars"] or 0) for x in v):,} 字</span></a>'
        for u, v in sorted(ups.items(), key=lambda kv: -len(kv[1])))
    recent_html = ''.join(card(d, ' · 入库 ' + d['add']) for d in recent)
    inner = (f'<h1>转写库</h1><div class="meta">{len(docs)} 篇 · '
             f'{sum(int(d["chars"] or 0) for d in docs):,} 字</div>'
             f'<input id="q" placeholder="全文搜索…" autocomplete="off">'
             f'<div id="r"></div><div id="home">'
             f'<div class="sec">☁ 云端转写 · 备用（Mac 热键不灵时用）</div>'
             f'<input id="cu" placeholder="粘贴 B站 视频链接" autocomplete="off">'
             f'<div class="bar"><button class="cb" data-m="T">T 免费</button>'
             f'<button class="cb" data-m="Y">Y 精修</button></div>'
             f'<div id="cs" class="hit"></div><div id="cloud"></div>'
             f'<h2>★ 我的收藏<span class="n">权重 ≥ 0.2</span></h2>'
             f'<div id="fav"><div class="empty">还没有。点两次星（权重到 0.2）就会出现在这里。</div></div>'
             f'<h2>最近添加</h2>{recent_html}'
             f'<h2>按 UP 主<span class="n">{len(ups)} 位</span></h2>{uplist}</div>')
    allcards = json.dumps([{'b': d['bv'].lower(), 'n': d['title'], 'u': d['up'], 'p': d['pub'],
                            'd': d['dur'], 'c': d['chars'], 'f': '豆包' in d['src']} for d in docs], ensure_ascii=False)
    home_js = f'''<script>{wjs}
const ALL={allcards};
function cardHTML(d){{const tag=d.f?'':'<span class="tag">快车道</span>';
 return '<div class="card"><a href="/d/'+d.b+'.html"><b>'+esc(d.n)+'</b><span class="meta">'+
  esc(d.u)+' · '+esc(d.p)+' · '+esc(d.d)+' · '+esc(d.c)+' 字'+tag+
  '</span></a><div class="foot"><span class="wbar"><i data-w="'+d.b+'"></i></span>'+
  '<span class="wt"><span class="num" data-n="'+d.b+'"></span>'+
  '<span class="star" data-bv="'+d.b+'">★</span></span></div></div>';}}
function esc(s){{return String(s||'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}
function paintAll(){{
 const f=ALL.filter(d=>nOf(W[d.b]||{{}})>=FAVN)
   .sort((a,b)=>nOf(W[b.b])-nOf(W[a.b]));
 const box=document.getElementById('fav');
 if(box)box.innerHTML=f.length?f.map(cardHTML).join('')
   :'<div class="empty">还没有。点两次星（权重到 0.2）就会出现在这里。</div>';
 bindW();}}
function bindW(){{
 document.querySelectorAll('.star').forEach(e=>{{
  const o=W[e.dataset.bv]||{{}};
  e.classList.toggle('on',nOf(o)>=FAVN);
  e.onclick=ev=>{{ev.preventDefault();ev.stopPropagation();
   bump(e.dataset.bv,1);paintAll();}};}});
 document.querySelectorAll('.num[data-n]').forEach(e=>{{
  const o=W[e.dataset.n]||{{}};const n=nOf(o);
  e.textContent=n?fmt(o):'';e.classList.toggle('on',n>=FAVN);}});
 document.querySelectorAll('[data-w]').forEach(e=>{{
  const o=W[e.dataset.w]||{{}};e.style.width=(wOf(o)*100)+'%';}});}}
lload();paintAll();pull().then(paintAll);
{CLOUD_JS}
{SEARCH_JS}</script>'''
    (SITE / 'index.html').write_text(shell('转写库', inner, nav(), home_js), encoding='utf-8')

    # ── 全部页 ──
    months = sorted({d['pub'][:7] for d in docs if d['pub']}, reverse=True)
    sel = (f'<div class="bar">'
           f'<select id="fu"><option value="">全部 UP 主</option>'
           + ''.join(f'<option>{E(u)}</option>' for u in sorted(ups)) + '</select>'
           f'<select id="fm"><option value="">全部时间</option>'
           + ''.join(f'<option>{m}</option>' for m in months) + '</select>'
           f'<select id="fq"><option value="">全部质量</option>'
           f'<option value="fine">只看精修</option><option value="fast">只看快车道</option>'
           f'</select></div>')
    inner2 = (f'<h1>全部文稿</h1><div class="meta" id="cnt">{len(docs)} 篇</div>'
              f'<input id="q" placeholder="全文搜索…" autocomplete="off">'
              f'<div id="r"></div>{sel}<div id="list"></div>')
    all_js = f'''<script>{wjs}
const ALL={allcards};
function esc(s){{return String(s||'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}
function cardHTML(d){{const tag=d.f?'':'<span class="tag">快车道</span>';
 return '<div class="card"><a href="/d/'+d.b+'.html"><b>'+esc(d.n)+'</b><span class="meta">'+
  esc(d.u)+' · '+esc(d.p)+' · '+esc(d.d)+' · '+esc(d.c)+' 字'+tag+
  '</span></a><div class="foot"><span class="wbar"><i data-w="'+d.b+'"></i></span>'+
  '<span class="wt"><span class="num" data-n="'+d.b+'"></span>'+
  '<span class="star" data-bv="'+d.b+'">★</span>'+
  '<span class="stp"><button data-dec="'+d.b+'">−</button>'+
  '<button data-inc="'+d.b+'">＋</button></span></span></div></div>';}}
const fu=document.getElementById('fu'),fm=document.getElementById('fm'),
      fq=document.getElementById('fq'),L=document.getElementById('list'),
      CN=document.getElementById('cnt');
function render(){{
 let v=ALL.filter(d=>(!fu.value||d.u===fu.value)&&(!fm.value||(d.p||'').startsWith(fm.value))
   &&(!fq.value||(fq.value==='fine'?d.f:!d.f)));
 v.sort((a,b)=>(b.p||'').localeCompare(a.p||''));
 CN.textContent=v.length+' 篇 · '+v.reduce((s,d)=>s+(+d.c||0),0).toLocaleString()+' 字';
 let out='',cur='';
 for(const d of v){{const m=(d.p||'').slice(0,7)||'未知';
  if(m!==cur){{cur=m;out+='<div class="sec">'+m+'</div>';}}
  out+=cardHTML(d);}}
 L.innerHTML=out||'<div class="empty">没有符合条件的文稿</div>';
 bindW();}}
function bindW(){{
 document.querySelectorAll('.star').forEach(e=>{{
  const o=W[e.dataset.bv]||{{}};
  e.classList.toggle('on',nOf(o)>=FAVN);
  e.onclick=ev=>{{ev.preventDefault();ev.stopPropagation();
   bump(e.dataset.bv,1);bindW();}};}});
 document.querySelectorAll('[data-inc]').forEach(e=>{{
  e.onclick=ev=>{{ev.preventDefault();bump(e.dataset.inc,1);bindW();}};}});
 document.querySelectorAll('[data-dec]').forEach(e=>{{
  e.onclick=ev=>{{ev.preventDefault();bump(e.dataset.dec,-1);bindW();}};}});
 document.querySelectorAll('.num[data-n]').forEach(e=>{{
  const o=W[e.dataset.n]||{{}};const n=nOf(o);
  e.textContent=n?fmt(o):'0.0';e.classList.toggle('on',n>=FAVN);}});
 document.querySelectorAll('[data-w]').forEach(e=>{{
  const o=W[e.dataset.w]||{{}};e.style.width=(wOf(o)*100)+'%';}});}}
[fu,fm,fq].forEach(e=>e.onchange=render);
const h=new URLSearchParams(location.hash.slice(1));
if(h.get('up'))fu.value=h.get('up');
lload();render();pull().then(render);
{SEARCH_JS}</script>'''
    (SITE / 'all.html').write_text(shell('全部文稿', inner2, nav('all.html'), all_js),
                                   encoding='utf-8')

    # ── 说明页 ──
    (SITE / 'help.html').write_text(
        shell('说明', HELP.replace('{SYNC}', SYNC_RW if key else SYNC_RO), nav('help.html')),
        encoding='utf-8')

    # ── 云端文稿阅读页：c.html?bv=BV…，正文从 /api/cloud 现取 ──
    (SITE / 'c.html').write_text(
        shell('云端文稿', '<div id="doc"><div class="empty">载入中…</div></div>', nav(), C_JS),
        encoding='utf-8')

    # ── 搜索索引与杂项 ──
    (SITE / 'search.json').write_text(json.dumps(
        [{'b': d['bv'].lower(), 'n': d['title'],
          't': re.sub(r'\s+', ' ', re.sub(r'\*\*(.+?)\*\*：', r'\1：', d['text']))}
         for d in docs], ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (SITE / 'robots.txt').write_text('User-agent: *\nDisallow: /\n', encoding='utf-8')

    # 生成的 JS 必须先过语法检查——模板拼接出来的代码，肉眼看不出断在哪
    bad = []
    for f in sorted(SITE.rglob('*.html')):
        js = ''.join(re.findall(r'<script>(.*?)</script>', f.read_text(encoding='utf-8'), re.S))
        if not js:
            continue
        r = subprocess.run(['node', '--check', '/dev/stdin'], input=js,
                           capture_output=True, text=True)
        if r.returncode:
            bad.append(f'{f.relative_to(SITE)}: {r.stderr.splitlines()[0][:80]}')
    if bad:
        print('  ✗ 生成的 JS 有语法错误，已中止发布：')
        for b in bad:
            print(f'      {b}')
        raise SystemExit(2)

    mb = sum(f.stat().st_size for f in SITE.rglob('*') if f.is_file()) / 1048576
    print(f'  {len(docs)} 篇 · {sum(int(d["chars"] or 0) for d in docs):,} 字 · '
          f'{len(ups)} 位 UP 主 · 站点 {mb:.2f} MB')
    if mb > 8:
        print('  ! 搜索索引超 8MB，该改成按需加载了')
    return docs


SEARCH_JS = '''
const q=document.getElementById('q'),r=document.getElementById('r');
const HOME=document.getElementById('home'),LIST=document.getElementById('list');
let idx=null,busy=false;
async function loadIdx(){if(idx||busy)return;busy=true;
 r.innerHTML='<div class="hit">载入索引…</div>';
 idx=await (await fetch('/search.json')).json();busy=false;}
async function runSearch(){const k=q.value.trim();
 const other=HOME||LIST;
 if(!k){r.innerHTML='';if(other)other.style.display='';return}
 await loadIdx();if(other)other.style.display='none';
 let out=[],n=0;
 for(const d of idx){const t=d.t;let i=-1,hits=[];
  while((i=t.indexOf(k,i+1))>=0&&hits.length<3){
   hits.push(esc(t.slice(Math.max(0,i-26),i))+'<mark>'+esc(k)+'</mark>'+
             esc(t.slice(i+k.length,i+k.length+34)));}
  if(hits.length){n++;out.push('<a class="card" href="/d/'+d.b+'.html"><b>'+esc(d.n)+'</b>'+
   hits.map(h=>'<div class="hit">…'+h+'…</div>').join('')+'</a>');}}
 r.innerHTML='<div class="sec">命中 '+n+' 篇</div>'+
   (out.join('')||'<div class="empty">没找到</div>');}
let stm;q.addEventListener('input',()=>{clearTimeout(stm);stm=setTimeout(runSearch,180)});
'''


CLOUD_JS = r"""
const CP='zx-cloud-pass';
function cget(){try{return localStorage.getItem(CP)||''}catch(e){return ''}}
function cset(p){try{p?localStorage.setItem(CP,p):localStorage.removeItem(CP)}catch(e){}}
async function capi(b){const r=await fetch('/api/cloud',{method:'POST',
 headers:{'content-type':'application/json'},body:JSON.stringify(b)});
 try{return await r.json()}catch(e){return {error:'http_'+r.status,msg:'服务出错（'+r.status+'）'}}}
function csay(h){document.getElementById('cs').innerHTML=h}
function cbtn(d){document.querySelectorAll('.cb').forEach(b=>b.disabled=d)}
function cdone(j){csay('✓ 已出稿：<a href="/c.html?bv='+j.bvid+'">'+esc(j.title)+'</a>'+
 (j.note?'（'+esc(j.note)+'）':''));loadCloud();}
async function cgo(mode){
 const url=document.getElementById('cu').value.trim();
 if(!/bilibili\.com|b23\.tv|bili2233\.cn|BV[0-9A-Za-z]{10}/.test(url)){csay('先粘贴 B站 视频链接');return}
 const pass=cget()||prompt('云端转写口令（装机时生成的那串，每台设备输一次）')||'';
 if(!pass)return;
 cbtn(true);
 try{
  csay('解析中…');
  let j=await capi({url,mode:'info',pass});
  if(j.error==='bad_pass'){cset('');csay('口令不对，再点一次重新输入');return}
  if(j.error){csay(esc(j.msg||j.error));return}
  cset(pass);
  const m=j.meta;
  if(mode==='Y'&&!confirm('《'+m.title+'》\n'+m.up+' · '+Math.max(1,Math.round(m.dur/60))+' 分钟\n精修约 '+j.cost+' 元，确定？')){csay('');return}
  csay('《'+esc(m.title)+'》'+(mode==='T'?'取字幕中…':'提交中…'));
  j=await capi({url,mode,pass});
  if(j.error){csay(esc(j.msg||j.error));return}
  if(j.done){cdone(j);return}
  for(let i=1;i<=320;i++){
   await new Promise(r=>setTimeout(r,3000));
   let s={};try{s=await (await fetch('/api/cloud?job='+encodeURIComponent(j.job)+'&_='+Date.now())).json()}catch(e){}
   if(s.status==='done'){cdone(j);return}
   if(s.status==='error'){csay('失败：'+esc(s.msg));return}
   csay('《'+esc(j.title)+'》'+esc(s.msg||'排队中')+' · '+i*3+' 秒');}
  csay('还在跑，过一会儿刷新页面看「云端新稿」');
 }catch(e){csay('出错：'+esc(String(e)))}finally{cbtn(false)}
}
document.querySelectorAll('.cb').forEach(b=>b.onclick=()=>cgo(b.dataset.m));
async function loadCloud(){
 try{const j=await (await fetch('/api/cloud?list&_='+Date.now())).json();
  const have=new Set(ALL.map(d=>d.b));
  const v=(j.docs||[]).filter(d=>!have.has(d.bvid.toLowerCase()));
  document.getElementById('cloud').innerHTML=v.length?'<h2>☁ 云端新稿<span class="n">Mac 下次发布时收进文稿</span></h2>'+
   v.map(d=>'<a class="card" href="/c.html?bv='+d.bvid+'"><b>'+esc(d.title)+'</b><span class="meta">'+esc(d.up)+
   ' · '+esc(d.pub)+' · '+Math.max(1,Math.round(d.dur/60))+' 分 · '+d.chars+' 字<span class="tag">'+
   (d.mode==='Y'?'云端精修':'云端快车道')+'</span></span></a>').join(''):'';
 }catch(e){}}
loadCloud();
"""

C_JS = r"""<script>
const BV=new URLSearchParams(location.search).get('bv')||'';
const E=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const DUR=s=>s>=3600?Math.floor(s/3600)+'h'+Math.floor(s%3600/60)+'m':Math.floor(s/60)+'m'+(s%60)+'s';
(async()=>{const box=document.getElementById('doc');
 if(!/^BV[0-9A-Za-z]{10}$/.test(BV)){box.innerHTML='<div class="empty">链接不对</div>';return}
 try{const r=await fetch('/api/cloud?doc='+BV+'&_='+Date.now());if(!r.ok)throw new Error(r.status);
  const d=await r.json();document.title=d.title;
  const tag=d.mode==='Y'?'云端精修·未核':'云端快车道·可能有缺失';
  box.innerHTML='<h1>'+E(d.title)+'</h1><div class="meta">'+E(d.up)+' · '+E(d.pub)+' · '+DUR(d.dur)+' · '+
   d.chars+' 字<span class="tag">'+tag+'</span><br><a href="https://www.bilibili.com/video/'+BV+
   '/">在 B站 打开原视频</a></div><hr style="border:0;border-top:1px solid var(--line);margin:1.2rem 0">'+
   d.text.split('\n\n').map(p=>{const m=p.match(/^\*\*(.+?)\*\*：([\s\S]*)$/);
    return m?'<p class="t"><i>'+E(m[1])+'</i>'+E(m[2])+'</p>':'<p>'+E(p)+'</p>'}).join('');
 }catch(e){box.innerHTML='<div class="empty">没找到这篇。可能已经并入正式文稿，回首页找。</div>'}})();
</script>"""


def deploy():
    print('  部署到 Netlify…')
    cmd = ['netlify', 'deploy', '--prod', '--dir', str(SITE)]
    fn = ROOT / 'netlify' / 'functions'
    if fn.exists():
        cmd += ['--functions', str(fn)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = r.stdout + r.stderr
    m = re.search(r'(?:Website URL|Production URL):\s*<?(\S+?)>?\s*$', out, re.M)
    print(f'  ✓ {m.group(1)}' if m else out[-700:])
    return 0 if r.returncode == 0 else 1


def serve(port=8787):
    import http.server, functools, webbrowser, threading
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), h)
    print(f'  本地预览 http://127.0.0.1:{port}/   （Ctrl-C 结束）')
    print('  注意：/api/w 在本地不存在，收藏会退回 localStorage——只影响同步，不影响看排版')
    threading.Timer(0.6, lambda: webbrowser.open(f'http://127.0.0.1:{port}/')).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n  已停止')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--deploy', action='store_true', help='推到 Netlify（占额度，改完再做）')
    ap.add_argument('--serve', action='store_true', help='本地起服务预览')
    ap.add_argument('--build', action='store_true', help='（兼容旧写法，等同默认）')
    a = ap.parse_args()
    build()
    if a.deploy:
        sys.exit(deploy())
    if a.serve:
        sys.exit(serve())
    print('  未部署。本地预览 src/publish.py --serve ｜ 确定要推 src/publish.py --deploy')
    sys.exit(0)
