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
:root{--fs:19px;--lh:1.95}
body{margin:0;background:var(--bg);color:var(--fg);
 font:var(--fs)/var(--lh) -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",sans-serif;
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
.imp{display:inline-flex;align-items:center;gap:.12rem;flex:none}
.imp i{display:inline-block;width:1.25rem;height:1.25rem;cursor:pointer;position:relative}
.imp i::after{content:"";position:absolute;inset:.32rem;border-radius:50%;border:1.6px solid var(--dim);opacity:.55}
.imp i.on::after{background:var(--star);border-color:var(--star);opacity:1}
:root[data-theme="light"]{--bg:#fbfaf8;--fg:#23201c;--dim:#8a8378;--line:#e6e1d8;--card:#fff;--accent:#7a5c3e;--star:#d9a441;--chip:#f2eee6}
:root[data-theme="dark"]{--bg:#16150f;--fg:#e8e4dc;--dim:#918a7e;--line:#2e2a22;--card:#1e1c16;--accent:#c9a87c;--star:#e0b45a;--chip:#26231c}
:root[data-theme="sepia"]{--bg:#f4ecd8;--fg:#3b2f20;--dim:#8b7a5e;--line:#e2d5b8;--card:#f9f2e2;--accent:#8a5a2b;--star:#c8892b;--chip:#ebdfc4}
:root[data-font="serif"] body{font-family:"Songti SC","STSong","Noto Serif CJK SC",Georgia,serif}
#prog{position:fixed;top:0;left:0;height:3px;width:0;background:var(--star);z-index:20;transition:width .1s}
.toast{position:fixed;left:50%;bottom:1.4rem;transform:translateX(-50%);background:var(--card);border:1px solid var(--line);
 border-radius:10px;padding:.5rem .8rem;font-size:.85rem;box-shadow:0 4px 18px rgba(0,0,0,.18);z-index:30}
.toast button,.pop button{margin-left:.5rem;border:1px solid var(--line);border-radius:7px;background:var(--chip);color:var(--fg);
 padding:.2rem .55rem;font-size:.82rem;cursor:pointer}
mark.hl{background:rgba(217,164,65,.35);color:inherit;border-radius:2px;cursor:pointer}
mark.hl.note{border-bottom:2px solid var(--star)}
mark.fd{background:#7fb3ff66;color:inherit}mark.fd.cur{background:#7fb3ff}
.pop{position:absolute;z-index:40;background:var(--card);border:1px solid var(--line);border-radius:9px;padding:.35rem .4rem;
 font-size:.85rem;box-shadow:0 4px 18px rgba(0,0,0,.2);max-width:18rem}
.pop .q{color:var(--dim);font-size:.8rem;margin:.1rem .2rem .3rem}
.chips{display:flex;gap:.35rem;flex-wrap:wrap;margin:.6rem 0 .2rem}
.chips button{border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--dim);padding:.15rem .7rem;font-size:.8rem;cursor:pointer}
.chips button.on{background:var(--chip);color:var(--fg);border-color:var(--dim)}
.fsbar input{width:7rem;padding:.2rem .45rem;margin:0;font-size:.82rem;border-radius:7px}
.fsbar{display:flex;gap:.3rem;align-items:center;flex-wrap:wrap;font-size:.8rem;color:var(--dim);margin:.3rem 0 0}
.fsbar button{min-width:2.3rem;padding:.2rem .45rem;border:1px solid var(--line);border-radius:7px;
 background:var(--card);color:var(--fg);font-size:.85rem;cursor:pointer}
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
p.en{margin:0 0 .35rem;font-size:.95rem;line-height:1.75}
p.zh{margin:0 0 1.35rem;color:var(--dim)}
.ed{margin-top:2.4rem;border-top:1px solid var(--line);padding-top:.8rem}
.ed summary{color:var(--dim);font-size:.85rem;cursor:pointer}
.ed .bar{margin:.7rem 0 .3rem}
#gone{border-color:var(--accent)}
"""

WJS = """
// 重要度：0–5 档（每档 0.2），只由你点圆点设定，不会自己涨、也不会自己掉。
// 阅读记录（最近一次读 r、读过几次 o）单独记，只用来排「最近在读」，不影响重要度。
// 多设备合并：重要度看谁改得晚（ti），阅读记录取较新的。旧数据（0–10 档权重）折半迁移。
const FAVN=2, LK='transcribe-w', KEY='%(key)s', OLD=[0,3,6,8,9,9,10,10,10];
let W={};
function lv(o){if(!o)return 0;if(o.i!=null)return Math.max(0,Math.min(5,o.i|0));
 const n=o.n!=null?o.n:(o.s!=null?OLD[Math.min(o.s,8)]:0);return Math.floor(n/2)}
const nOf=o=>lv(o)*2, wOf=o=>lv(o)/5, fmt=o=>(lv(o)/5).toFixed(1);
function norm(o){o.i=lv(o);o.ti=o.ti||o.t||0;delete o.n;delete o.s;return o}
function lload(){try{W=JSON.parse(localStorage.getItem(LK)||'{}')}catch(e){W={}}for(const k in W)norm(W[k])}
function lsave(){try{localStorage.setItem(LK,JSON.stringify(W))}catch(e){}}
async function pull(){try{const d=await (await fetch('/api/w?_='+Date.now())).json();
 if(d&&d.w)for(const k in d.w){const sv=norm(Object.assign({},d.w[k])),lo=W[k];
  if(!lo){W[k]=sv;continue}
  if((sv.ti||0)>(lo.ti||0)){lo.i=sv.i;lo.ti=sv.ti}
  if((sv.r||0)>(lo.r||0))lo.r=sv.r;lo.o=Math.max(lo.o||0,sv.o||0);lo.t=Math.max(lo.t||0,sv.t||0);
  if(sv.hl){const m=new Map((lo.hl||[]).map(h=>[h.q,h]));sv.hl.forEach(h=>{const x=m.get(h.q);if(!x||(h.t||0)>(x.t||0))m.set(h.q,h)});lo.hl=[...m.values()]}}}catch(e){}
 lsave()}
let tm=null;
function push(){if(!KEY)return;clearTimeout(tm);tm=setTimeout(async()=>{
 try{await fetch('/api/w',{method:'POST',headers:{'content-type':'application/json','x-key':KEY},
  body:JSON.stringify({w:W})})}catch(e){}},700)}
function setI(bv,i){const o=W[bv]||(W[bv]={i:0,o:0});o.i=Math.max(0,Math.min(5,i));o.ti=o.t=Date.now();lsave();push();return o.i}
function bump(bv,d){return setI(bv,lv(W[bv])+d)}
function open1(bv){const o=W[bv]||(W[bv]={i:0,o:0,ti:0});o.o=(o.o||0)+1;o.r=o.t=Date.now();lsave();push()}
// 五个圆点：点第 k 个设成 k 档；再点当前那档就清零
function paintImp(after){document.querySelectorAll('.imp[data-bv]').forEach(e=>{const bv=e.dataset.bv;
 if(!e.children.length)for(let k=1;k<=5;k++){const d=document.createElement('i');d.dataset.k=k;d.title=(k/5).toFixed(1);e.appendChild(d)}
 const i=lv(W[bv]);[...e.children].forEach(d=>{d.classList.toggle('on',+d.dataset.k<=i);
  d.onclick=ev=>{ev.preventDefault();ev.stopPropagation();const k=+d.dataset.k;setI(bv,k===lv(W[bv])?0:k);(after||paintImp)()}})})}
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


def lang(para):
    """段落是中文还是英文：汉字占比过三成算中文"""
    cjk = len(re.findall(r'[\u4e00-\u9fff]', para))
    return 'zh' if cjk > 0.3 * max(1, len(re.sub(r'\s', '', para))) else 'en'


def body_html(text):
    paras = [x.strip() for x in text.split('\n\n') if x.strip()]
    langs = [lang(x) for x in paras]
    both = 'en' in langs and 'zh' in langs          # 中英对照：两种语言都有
    out = []
    for para, lg in zip(paras, langs):
        sp = re.match(r'\*\*(.+?)\*\*：(.*)', para, re.S)
        if sp:
            out.append(f'<p class="t"><i>{E(sp.group(1))}</i>{E(sp.group(2))}</p>')
        else:
            out.append(f'<p class="{lg}">{E(para)}</p>' if both else f'<p>{E(para)}</p>')
    return '\n'.join(out)


def shell(title, inner, nav, script=''):
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow">'
            f'<title>{E(title)}</title><style>{CSS}</style>'
            '<script>try{var z=JSON.parse(localStorage.getItem("zx-type")||"{}");'
            'if(z.fs)document.documentElement.style.setProperty("--fs",z.fs+"px");'
            'if(z.lh)document.documentElement.style.setProperty("--lh",z.lh);'
            'if(z.th)document.documentElement.dataset.theme=z.th;if(z.ff)document.documentElement.dataset.font=z.ff}catch(e){}</script></head><body>'
            f'<header><div class="wrap">{nav}</div></header>'
            f'<div class="wrap">{inner}</div>'
            f'<div class="wrap"><footer>转写库 · {datetime.datetime.now():%Y-%m-%d %H:%M}'
            f'</footer></div>{script}</body></html>')


def nav(here=''):
    def it(href, label):
        return f'<b>{label}</b>' if href == here else f'<a href="/{href}">{label}</a>'
    return (it('', '首页') + ' · ' + it('all.html', '全部')
            + ' · ' + it('hl.html', '划线') + '<span class="sp"></span>' + it('help.html', '说明'))


def card(d, sub=''):
    fine = '豆包' in d['src']
    tag = ('<span class="tag">整理稿</span>' if d['manual'] else
           '' if fine else '<span class="tag">快车道</span>')
    bv = d['bv'].lower()
    return (f'<div class="card"><a href="/d/{bv}.html"><b>{E(d["title"])}</b>'
            f'<span class="meta">{E(d["up"])} · {E(d["pub"])}{" · " + E(d["dur"]) if d["dur"] else ""} · '
            f'{E(d["chars"])} 字{tag}{sub}</span></a>'
            f'<div class="foot"><span class="wbar"><i data-w="{bv}"></i></span>'
            f'<span class="wt"><span class="num" data-n="{bv}"></span>'
            f'<span class="imp" data-bv="{bv}"></span></span></div></div>')


HELP = """<h1>说明</h1>
<div class="meta">仓库：<a href="https://github.com/bobsybrashin/bili-transcribe-crosscheck">github.com/bobsybrashin/bili-transcribe-crosscheck</a></div>

<h2>0 · 一步到位</h2>
<p>设计思路：<b>人只做机器做不了的事，其余全交给脚本。</b>机器做不了的只有三样——给出仓库地址、点授权、填 API Key。所以整套东西只有两步，第二步就是验收。</p>
<table>
<tr><th></th><th>你做什么</th><th>脚本做什么</th></tr>
<tr><td>第 1 步</td><td>在 Mac 终端粘贴一行（仓库 README 第一段就是）：<br><code>zsh -c "$(curl -fsSL https://raw.githubusercontent.com/bobsybrashin/bili-transcribe-crosscheck/main/install.sh)"</code><br>答 3 个问题：① 仓库地址 ② 授权（Netlify 授权页点 Authorize、钥匙串点「始终允许」）③ 豆包 API Key</td><td>装工具、拉仓库、还原站上已有文稿、取 B站 登录态、对好站点密钥、放好云端密钥、绑快捷键，最后真跑一遍 T、Y 两条链路自检</td></tr>
<tr><td>第 2 步</td><td>复制 B站 链接，按 <kbd>⌃⌘T</kbd> 免费 或 <kbd>⌃⌘Y</kbd> 精修</td><td>出稿，放上首页「新稿」区（不发布、不花额度），弹通知并打开任务页：成功写字数、花费、待核项；失败写卡在哪一步、原因、怎么办</td></tr>
<tr><td>整理稿</td><td>不在 B站 的视频、英文材料、自己整理的文字：存成 .md / .txt，在访达里选中按 <kbd>⌃⌘U</kbd>（英文一段、中文一段交替就是中英对照）</td><td>收进文稿，放上首页「新稿」区，弹通知并打开任务页</td></tr>
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
<tr><td>6</td><td>第一次按热键可能弹「允许访问文稿文件夹」，点允许即可；按了没反应看 ~/Library/Logs/转写热键.log</td></tr>
<tr><td>7</td><td>免费路线要视频自带中文字幕</td></tr>
<tr><td>8</td><td>云端精修单条 ≤ 2 小时，没有热词表和双源核对</td></tr>
<tr><td>9</td><td>Netlify 免费额度 300/月硬上限，每次部署 15；出稿不花，发布才花</td></tr>
<tr><td>10</td><td>整理稿只收 .md / .txt；⌃⌘U 只在访达里有效</td></tr>
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

<h2>2 · 重要度怎么算</h2>
<table>
<tr><th>动作</th><th>结果</th></tr>
<tr><td>点第 k 个圆点</td><td>重要度设为 k × 0.2（一个点 0.2，五个点 1.0）</td></tr>
<tr><td>再点当前那一档</td><td>清零</td></tr>
<tr><td>打开、阅读</td><td><b>不改</b>重要度，只记进「最近在读」</td></tr>
<tr><td>放着不管</td><td><b>不会掉</b>——重要度是你的决定，不该自己变</td></tr>
</table>
<p>首页「重要」按重要度从高到低排；「全部」页可以「按重要度」排序。旧的 0–10 档权重已经折半换算过来。各设备之间同步：重要度以最后一次改的为准。</p>

<h2>3 · 其他</h2>

<h3>怎么加新稿子</h3>
<p>在 Mac 上<b>复制视频链接 → 按 <kbd>⌃⌘T</kbd> / <kbd>⌃⌘Y</kbd></b>，出稿后弹通知。不在 Mac 前就用首页「云端转写」，手机也能用。</p>
<p>云端精修没有热词表、也不做双源核对，标「云端精修·未核」；要紧的稿子还是回 Mac 走精修。</p>
<p><b>新 UP 主的第一条别直接走精修</b>——热词表在识别那一刻生效，没有表等于白花钱。先配好 <code>tables/hot/&lt;UP主&gt;.json</code> 再跑。</p>

<h3>删掉不要的</h3>
<p>每篇文稿、每条任务的页面底部都有「编辑」。删任务记录立刻生效；删文稿网页上立刻隐藏、可以撤销，Mac 下次发布时把本机那份挪进回收站，站上那页随之消失。要云端口令。</p>

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
        docs.append({'bv': fm.get('bvid') or fm.get('id') or p.stem, 'title': fm.get('title', p.stem),
                     'manual': not fm.get('bvid'), 'url': fm.get('url', ''), 'note': fm.get('note', ''),
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
        if d['manual']:
            tag = '<span class="tag">整理稿</span>'
            link = (f'<a href="{E(d["url"])}">打开原文</a>' if d['url'] else '') + \
                   (f'<br>{E(d["note"])}' if d['note'] else '') + f'<br>{E(d["src"])}'
        else:
            tag = '' if fine else '<span class="tag">快车道·可能有缺失</span>'
            link = f'<a href="https://www.bilibili.com/video/{d["bv"]}/">在 B站 打开原视频</a>'
        head = (f'<h1>{E(d["title"])}</h1><div class="meta">{E(d["up"])} · {E(d["pub"])}'
                f'{" · " + E(d["dur"]) if d["dur"] else ""} · {E(d["chars"])} 字{tag}<br>{link}'
                f'</div><hr style="border:0;border-top:1px solid var(--line);margin:1.2rem 0">')
        n = ('<a href="/">首页</a> · <a href="/all.html">全部</a><span class="sp"></span>'
             f'<span class="num rnum"></span>'
             f'<span class="imp" data-bv="{d["bv"].lower()}"></span>')
        js = (f'<script>{wjs}\n{TYPE_JS}\nlload();const BV="{d["bv"].lower()}";'
              'const nm=document.querySelector(".rnum");'
              'function paint(){const o=W[BV]||{};const n=nOf(o);paintImp(paint);'
              'nm.textContent=n?fmt(o):"";nm.className="rnum"+(n>=FAVN?" on":"");}'
              'paint();open1(BV);pull().then(paint);'
              'typeBar(document.querySelector(".wrap .meta"));'
              'initReader(BV,document.querySelectorAll(".wrap")[1]);</script>')
        edit = (f'<script>{EDIT_JS}\ninitDocEdit({json.dumps(d["bv"])},'
                f'{json.dumps(d["title"], ensure_ascii=False)});</script>').replace('</', '<\\/').replace('<\\/script>', '</script>')
        (SITE / 'd' / f'{d["bv"].lower()}.html').write_text(
            shell(d['title'], GONE + head + body_html(d['text']) + DOC_EDIT, n, js + edit), encoding='utf-8')

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
             f'<div id="cs" class="hit"></div><div id="tasks"></div>'
             f'<h2>重要<span class="n">你定的重要度，从高到低</span>'
             f'<a href="#" id="rnd" style="float:right;font-size:.85rem;font-weight:400">随手翻一篇 →</a></h2>'
             f'<div id="fav"></div>'
             f'<h2>最近在读</h2><div id="reading"></div>'
             f'<h2>最近添加</h2><div id="recent">{recent_html}</div>'
             f'<h2>按 UP 主<span class="n">{len(ups)} 位</span></h2>{uplist}</div>')
    allcards = json.dumps([{'b': d['bv'].lower(), 'n': d['title'], 'u': d['up'], 'p': d['pub'],
                            'd': d['dur'], 'c': d['chars'], 'f': '豆包' in d['src'] or d['manual'],
                            'm': d['manual']} for d in docs], ensure_ascii=False)
    home_js = f'''<script>{wjs}
const ALL={allcards};
function cardHTML(d){{const tag=d.m?'<span class="tag">整理稿</span>':d.f?'':'<span class="tag">快车道</span>';
 return '<div class="card"><a href="'+(d.h||'/d/'+d.b+'.html')+'"><b>'+esc(d.n)+'</b><span class="meta">'+
  esc(d.u)+' · '+esc(d.p)+(d.d?' · '+esc(d.d):'')+' · '+esc(d.c)+' 字'+tag+
  '</span></a><div class="foot"><span class="wbar"><i data-w="'+d.b+'"></i></span>'+
  '<span class="wt"><span class="num" data-n="'+d.b+'"></span>'+
  '<span class="imp" data-bv="'+d.b+'"></span></span></div></div>';}}
function esc(s){{return String(s||'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}
function paintAll(){{
 const f=ALL.filter(d=>lv(W[d.b])>0).sort((a,b)=>lv(W[b.b])-lv(W[a.b])||(W[b.b].ti||0)-(W[a.b].ti||0));
 const box=document.getElementById('fav');
 if(box)box.innerHTML=f.length?f.map(cardHTML).join('')
   :'<div class="empty">还没有。点卡片右下角的圆点给文稿定重要度（一个点 0.2，五个点 1.0），定了就不会自己掉。</div>';
 const rd=ALL.filter(d=>W[d.b]&&W[d.b].r).sort((a,b)=>W[b.b].r-W[a.b].r).slice(0,5);
 const rb=document.getElementById('reading');
 if(rb)rb.innerHTML=rd.length?rd.map(cardHTML).join(''):'<div class="empty">还没读过。</div>';
 bindW();}}
function bindW(){{
 paintImp(paintAll);
 document.querySelectorAll('.num[data-n]').forEach(e=>{{
  const o=W[e.dataset.n]||{{}};const n=nOf(o);
  e.textContent=n?fmt(o):'';e.classList.toggle('on',n>=FAVN);}});
 document.querySelectorAll('[data-w]').forEach(e=>{{
  const o=W[e.dataset.w]||{{}};e.style.width=(wOf(o)*100)+'%';}});}}
lload();paintAll();pull().then(paintAll);
document.getElementById('rnd').onclick=e=>{{e.preventDefault();
 const pool=ALL.filter(d=>lv(W[d.b])>=3),src=pool.length?pool:ALL,d=src[Math.floor(Math.random()*src.length)];
 location.href=d.h||'/d/'+d.b+'.html'}};
{NEW_JS}
{EDIT_JS}
const _bw=bindW;bindW=function(){{_bw();hideDel()}};loadDel().then(hideDel);
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
           f'<option value="manual">只看整理稿</option>'
           f'</select><select id="fs"><option value="">按日期</option><option value="imp">按重要度</option>'
           f'</select></div>')
    inner2 = (f'<h1>全部文稿</h1><div class="meta" id="cnt">{len(docs)} 篇</div>'
              f'<input id="q" placeholder="全文搜索…" autocomplete="off">'
              f'<div id="r"></div>{sel}<div id="list"></div>')
    all_js = f'''<script>{wjs}
const ALL={allcards};
function esc(s){{return String(s||'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}
function cardHTML(d){{const tag=d.m?'<span class="tag">整理稿</span>':d.f?'':'<span class="tag">快车道</span>';
 return '<div class="card"><a href="'+(d.h||'/d/'+d.b+'.html')+'"><b>'+esc(d.n)+'</b><span class="meta">'+
  esc(d.u)+' · '+esc(d.p)+(d.d?' · '+esc(d.d):'')+' · '+esc(d.c)+' 字'+tag+
  '</span></a><div class="foot"><span class="wbar"><i data-w="'+d.b+'"></i></span>'+
  '<span class="wt"><span class="num" data-n="'+d.b+'"></span>'+
  '<span class="imp" data-bv="'+d.b+'"></span></span></div></div>';}}
const fu=document.getElementById('fu'),fm=document.getElementById('fm'),
      fq=document.getElementById('fq'),fs=document.getElementById('fs'),L=document.getElementById('list'),
      CN=document.getElementById('cnt');
function render(){{
 let v=ALL.filter(d=>(!fu.value||d.u===fu.value)&&(!fm.value||(d.p||'').startsWith(fm.value))
   &&(!fq.value||(fq.value==='manual'?d.m:fq.value==='fine'?(d.f&&!d.m):!d.f)));
 v.sort((a,b)=>(b.p||'').localeCompare(a.p||''));
 if(fs.value==='imp')v.sort((a,b)=>lv(W[b.b])-lv(W[a.b]));
 CN.textContent=v.length+' 篇 · '+v.reduce((s,d)=>s+(+d.c||0),0).toLocaleString()+' 字';
 let out='',cur='';
 for(const d of v){{const m=fs.value==='imp'?['不重要','0.2','0.4','0.6','0.8','1.0'][lv(W[d.b])]:(d.p||'').slice(0,7)||'未知';
  if(m!==cur){{cur=m;out+='<div class="sec">'+m+'</div>';}}
  out+=cardHTML(d);}}
 L.innerHTML=out||'<div class="empty">没有符合条件的文稿</div>';
 bindW();}}
function bindW(){{
 paintImp(()=>{{if(fs.value==='imp')render();else bindW()}});
 document.querySelectorAll('.num[data-n]').forEach(e=>{{
  const o=W[e.dataset.n]||{{}};const n=nOf(o);
  e.textContent=n?fmt(o):'0.0';e.classList.toggle('on',n>=FAVN);}});
 document.querySelectorAll('[data-w]').forEach(e=>{{
  const o=W[e.dataset.w]||{{}};e.style.width=(wOf(o)*100)+'%';}});}}
[fu,fm,fq,fs].forEach(e=>e.onchange=render);
const h=new URLSearchParams(location.hash.slice(1));
if(h.get('up'))fu.value=h.get('up');
lload();render();pull().then(render);
{NEW_JS}
loadNew().then(v=>{{if(v.length){{ALL.push(...v);render()}}}});
{EDIT_JS}
const _bw=bindW;bindW=function(){{_bw();hideDel()}};loadDel().then(hideDel);
{SEARCH_JS}</script>'''
    (SITE / 'all.html').write_text(shell('全部文稿', inner2, nav('all.html'), all_js),
                                   encoding='utf-8')

    # ── 说明页 ──
    (SITE / 'help.html').write_text(
        shell('说明', HELP.replace('{SYNC}', SYNC_RW if key else SYNC_RO), nav('help.html')),
        encoding='utf-8')

    # ── 划线页：所有划线和笔记，按文稿归组 ──
    (SITE / 'hl.html').write_text(shell('划线', '<h1>划线与笔记</h1><div class="meta" id="hn"></div><div id="hl"></div>', nav('hl.html'),
        f'<script>{wjs}</script>' + HL_JS), encoding='utf-8')

    # ── 任务页：t.html?id=…，一次转写走到哪一步、成没成、卡在哪、怎么办 ──
    (SITE / 't.html').write_text(
        shell('转写任务', '<div id="task"><div class="empty">载入中…</div></div>' + TASK_EDIT, nav(),
              f'<script>{EDIT_JS}</script>' + T_JS), encoding='utf-8')

    # ── 新转写的阅读页：c.html?bv=…，正文从 /api/cloud 现取；发布成正式页之前用它，样子和正式页一样 ──
    (SITE / 'c.html').write_text(
        shell('文稿', GONE + '<div id="doc"><div class="empty">载入中…</div></div>' + DOC_EDIT, nav(),
              f'<script>{wjs}\n{TYPE_JS}\n{EDIT_JS}</script>' + C_JS),
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
 idx=await (await fetch('/search.json')).json();
 if(typeof loadNew==='function')for(const d of await loadNew()){
  try{const x=await (await fetch('/api/cloud?doc='+d.id)).json();
   idx.unshift({b:d.b,h:d.h,n:d.n,t:x.text.replace(/\*\*(.+?)\*\*：/g,'$1：').replace(/\s+/g,' ')})}catch(e){}}
 busy=false;}
async function runSearch(){const k=q.value.trim();
 const other=HOME||LIST;
 if(!k){r.innerHTML='';if(other)other.style.display='';return}
 await loadIdx();if(other)other.style.display='none';
 let out=[],n=0;
 for(const d of idx){const t=d.t;let i=-1,hits=[];
  while((i=t.indexOf(k,i+1))>=0&&hits.length<3){
   hits.push(esc(t.slice(Math.max(0,i-26),i))+'<mark>'+esc(k)+'</mark>'+
             esc(t.slice(i+k.length,i+k.length+34)));}
  if(hits.length){n++;out.push('<a class="card" href="'+(d.h||'/d/'+d.b+'.html')+'"><b>'+esc(d.n)+'</b>'+
   hits.map(h=>'<div class="hit">…'+h+'…</div>').join('')+'</a>');}}
 r.innerHTML='<div class="sec">命中 '+n+' 篇</div>'+
   (out.join('')||'<div class="empty">没找到</div>');if(typeof hideDel==='function')hideDel();}
let stm;q.addEventListener('input',()=>{clearTimeout(stm);stm=setTimeout(runSearch,180)});
'''


TYPE_JS = r"""
function typeBar(host){
 let z={};try{z=JSON.parse(localStorage.getItem('zx-type')||'{}')}catch(e){}
 const D=document.documentElement,R=D.style,save=()=>{try{localStorage.setItem('zx-type',JSON.stringify(z))}catch(e){}},
  ap=()=>{R.setProperty('--fs',(z.fs||19)+'px');R.setProperty('--lh',z.lh||1.95);
   if(z.th)D.dataset.theme=z.th;else delete D.dataset.theme;if(z.ff)D.dataset.font=z.ff;else delete D.dataset.font};
 const TH=['','light','dark','sepia'],THN={'':'跟随系统',light:'浅色',dark:'深色',sepia:'护眼'};
 host.insertAdjacentHTML('beforeend','<div class="fsbar">字号 <button data-a="-">A−</button><button data-a="+">A＋</button>'+
  '<button data-a="l">行距</button><button data-a="t">主题</button><button data-a="f">字体</button><button data-a="0">默认</button>'+
  '<input id="fnd" placeholder="文内查找 /" autocomplete="off"><span id="fndn"></span><button data-a="c">复制全文</button></div>');
 host.querySelectorAll('.fsbar button').forEach(b=>b.onclick=()=>{const a=b.dataset.a,f=z.fs||19;
  if(a==='-')z.fs=Math.max(15,f-1);if(a==='+')z.fs=Math.min(26,f+1);
  if(a==='l')z.lh=(z.lh||1.95)>=2.2?1.75:+((z.lh||1.95)+0.2).toFixed(2);
  if(a==='t'){z.th=TH[(TH.indexOf(z.th||'')+1)%TH.length];toast('主题：'+THN[z.th])}
  if(a==='f'){z.ff=z.ff==='serif'?'':'serif';toast(z.ff?'衬线字体':'无衬线字体')}
  if(a==='0')z={};
  if(a==='c'){copyAll();return}
  ap();save()})}
function toast(h,ms){document.querySelectorAll('.toast').forEach(x=>x.remove());const t=document.createElement('div');
 t.className='toast';t.innerHTML=h;document.body.appendChild(t);setTimeout(()=>t.remove(),ms||2200);return t}
function copyAll(){const t=document.querySelector('h1').textContent+'\n\n'+ART().map(p=>p.innerText).join('\n\n');
 (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>toast('已复制全文'),()=>toast('复制失败，请手动选择'))}
let ART=()=>[];
// 阅读器：进度条与续读、阅读时长、按说话人筛选、划线与笔记、文内查找
function initReader(bv,root){
 ART=()=>[...root.querySelectorAll('p')].filter(p=>!p.closest('.meta,.card,.ed,.toast,.pop'));
 const art=ART();
 const bar=document.createElement('div');bar.id='prog';document.body.appendChild(bar);
 const PK='zx-pos-'+bv,H=document.documentElement,frac=()=>{const m=H.scrollHeight-H.clientHeight;return m>0?H.scrollTop/m:0};
 let st=null;addEventListener('scroll',()=>{bar.style.width=(frac()*100)+'%';clearTimeout(st);
  st=setTimeout(()=>{try{localStorage.setItem(PK,frac().toFixed(4))}catch(e){}},300)},{passive:true});
 let sv=0;try{sv=+localStorage.getItem(PK)||0}catch(e){}
 if(sv>0.03&&sv<0.97){const t=toast('上次读到 '+Math.round(sv*100)+'%<button>接着读</button>',9000);
  t.querySelector('button').onclick=()=>{H.scrollTop=sv*(H.scrollHeight-H.clientHeight);t.remove()}}
 const n=art.reduce((s,p)=>s+p.textContent.length,0),meta=root.querySelector('.meta');
 if(meta&&!meta.dataset.rt){meta.dataset.rt=1;meta.insertAdjacentHTML('afterbegin','约 '+Math.max(1,Math.round(n/450))+' 分钟读完 · ')}
 // 说话人筛选
 const who=[...new Set(art.filter(p=>p.classList.contains('t')).map(p=>p.querySelector('i').textContent))];
 if(who.length>=2){const c=document.createElement('div');c.className='chips';
  c.innerHTML='<button class="on" data-w="">全部</button>'+who.map(w=>'<button data-w="'+w+'">只看'+w+'</button>').join('');
  art[0].before(c);c.querySelectorAll('button').forEach(b=>b.onclick=()=>{c.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
   const w=b.dataset.w;art.forEach(p=>p.style.display=!w||!p.classList.contains('t')||p.querySelector('i').textContent===w?'':'none')})}
 // 划线
 const hls=()=>(W[bv]&&W[bv].hl||[]).filter(h=>!h.del);
 function wrap(q,cls,attrs){for(const p of art){const tw=document.createTreeWalker(p,NodeFilter.SHOW_TEXT);let nd;
  while(nd=tw.nextNode()){if(nd.parentNode.closest('mark'))continue;const i=nd.data.indexOf(q);if(i<0)continue;
   const r=document.createRange();r.setStart(nd,i);r.setEnd(nd,i+q.length);const m=document.createElement('mark');m.className=cls;
   Object.assign(m.dataset,attrs||{});r.surroundContents(m);return m}}return null}
 function paintHL(){root.querySelectorAll('mark.hl').forEach(m=>m.replaceWith(...m.childNodes));art.forEach(p=>p.normalize());
  hls().forEach(h=>wrap(h.q,'hl'+(h.n?' note':''),{q:h.q}))}
 function saveHL(q,note){const o=W[bv]||(W[bv]={i:0,o:0,ti:0});o.hl=(o.hl||[]).filter(h=>h.q!==q);
  o.hl.push({q,n:note||'',t:Date.now(),d:document.querySelector('h1').textContent,u:location.pathname+location.search});
  o.t=Date.now();lsave();push();paintHL()}
 function delHL(q){const o=W[bv];if(!o)return;o.hl=(o.hl||[]).map(h=>h.q===q?{q,del:1,t:Date.now()}:h);o.t=Date.now();lsave();push();paintHL()}
 let pop=null;const close=()=>{if(pop){pop.remove();pop=null}};
 function popAt(rect,html){close();pop=document.createElement('div');pop.className='pop';pop.innerHTML=html;document.body.appendChild(pop);
  pop.style.top=(scrollY+rect.bottom+8)+'px';pop.style.left=Math.max(8,Math.min(innerWidth-pop.offsetWidth-8,scrollX+rect.left))+'px';return pop}
 document.addEventListener('mouseup',selCheck);document.addEventListener('touchend',()=>setTimeout(selCheck,30));
 function selCheck(e){if(e&&e.target&&e.target.closest&&e.target.closest('.pop'))return;
  const s=getSelection(),q=s.toString().trim();if(!q||q.length<2||q.length>400||!art.some(p=>p.contains(s.anchorNode))){return}
  const pp=popAt(s.getRangeAt(0).getBoundingClientRect(),'<button data-a="h">划线</button><button data-a="n">划线 + 笔记</button>');
  pp.onclick=ev=>{const a=ev.target.dataset.a;if(!a)return;const note=a==='n'?(prompt('笔记（可空）','')||''):'';
   saveHL(q,note);s.removeAllRanges();close();toast(note?'已划线并记笔记':'已划线')}}
 root.addEventListener('click',e=>{const m=e.target.closest('mark.hl');if(!m)return;const h=hls().find(x=>x.q===m.dataset.q);if(!h)return;
  const pp=popAt(m.getBoundingClientRect(),(h.n?'<div class="q">'+h.n.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</div>':'')+
   '<button data-a="e">'+(h.n?'改笔记':'加笔记')+'</button><button data-a="d">删除划线</button>');
  pp.onclick=ev=>{const a=ev.target.dataset.a;if(a==='d'){delHL(h.q);close()}if(a==='e'){const v=prompt('笔记',h.n||'');if(v!==null)saveHL(h.q,v);close()}}});
 document.addEventListener('mousedown',e=>{if(pop&&!e.target.closest('.pop'))close()});
 paintHL();
 // 文内查找
 const fi=document.getElementById('fnd'),fn=document.getElementById('fndn');let hits=[],cur=-1;
 if(fi){const clear=()=>{root.querySelectorAll('mark.fd').forEach(m=>m.replaceWith(...m.childNodes));art.forEach(p=>p.normalize());hits=[];cur=-1};
  fi.oninput=()=>{clear();const q=fi.value.trim();if(q.length<1){fn.textContent='';return}
   for(let k=0;k<500;k++){const m=wrap(q,'fd');if(!m)break;hits.push(m)}fn.textContent=hits.length?hits.length+' 处':'没有';if(hits.length)go(0)};
  const go=i=>{if(!hits.length)return;hits.forEach(m=>m.classList.remove('cur'));cur=(i+hits.length)%hits.length;hits[cur].classList.add('cur');
   hits[cur].scrollIntoView({block:'center'});fn.textContent=(cur+1)+'/'+hits.length};
  fi.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();go(cur+(e.shiftKey?-1:1))}if(e.key==='Escape'){fi.value='';clear();fn.textContent='';fi.blur()}};
  document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement!==fi&&!/INPUT|TEXTAREA/.test(document.activeElement.tagName)){e.preventDefault();fi.focus()}})}
 pull().then(paintHL)}
"""

NEW_JS = r"""
const DURS=s=>!s?'':s>=3600?Math.floor(s/3600)+'h'+Math.floor(s%3600/60)+'m':Math.floor(s/60)+'m'+(s%60)+'s';
let NEWV=null;
async function loadNew(){if(NEWV)return NEWV;
 try{const j=await (await fetch('/api/cloud?list&_='+Date.now())).json();const have=new Set(ALL.map(d=>d.b));
  NEWV=(j.docs||[]).filter(d=>!have.has(d.bvid.toLowerCase())).map(d=>({b:d.bvid.toLowerCase(),id:d.bvid,
   h:'/c.html?bv='+d.bvid,n:d.title,u:d.up,p:d.pub,d:DURS(d.dur),c:d.chars,f:d.mode!=='T',m:d.mode==='M',
   a:new Date(d.created).toISOString().slice(0,10)}))}catch(e){NEWV=[]}
 return NEWV}
"""

EDIT_JS = r"""
const CPK='zx-cloud-pass';
function epass(){let p='';try{p=localStorage.getItem(CPK)||''}catch(e){}return p||prompt('云端口令（装机时生成的那串，每台设备输一次）')||''}
async function eapi(body){const pass=epass();if(!pass)return null;let j={};
 try{const r=await fetch('/api/cloud',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(Object.assign({},body,{pass}))});j=await r.json()}catch(e){j={error:'net',msg:'网络不通'}}
 if(j.error==='bad_pass'){try{localStorage.removeItem(CPK)}catch(e){}alert('口令不对');return null}
 if(j.error){alert('没成功：'+(j.msg||j.error));return null}
 try{localStorage.setItem(CPK,pass)}catch(e){}return j}
let DEL=new Set();
async function loadDel(){try{const j=await (await fetch('/api/cloud?deleted&_='+Date.now())).json();
 DEL=new Set((j.ids||[]).map(x=>x.toLowerCase()))}catch(e){}return DEL}
function hideDel(){if(!DEL.size)return;document.querySelectorAll('a[href]').forEach(a=>{
 const m=(a.getAttribute('href')||'').match(/^\/(?:d\/([\w-]+)\.html|c\.html\?bv=([\w-]+))/);
 if(m&&DEL.has((m[1]||m[2]).toLowerCase()))(a.closest('.card')||a).style.display='none'})}
async function initDocEdit(id,title){
 const g=document.getElementById('gone'),b=document.getElementById('edDel');if(!g||!b)return;
 function paint(del){g.style.display=del?'':'none';b.textContent=del?'已删除':'删除这篇';b.disabled=del;
  g.innerHTML=del?'<b>这篇已删除</b><span class="meta">网页上已经隐藏，Mac 下次发布时从网站移除，本机那份挪进回收站。</span>'+
   '<div class="bar" style="margin:.6rem 0 0"><button class="cb" id="edUndo">撤销删除</button></div>':'';
  const u=document.getElementById('edUndo');if(u)u.onclick=async()=>{if(await eapi({action:'undeldoc',id}))paint(false)}}
 await loadDel();paint(DEL.has(id.toLowerCase()));
 b.onclick=async()=>{if(!confirm('删除《'+title+'》？\n网页上立刻隐藏，可以撤销。'))return;if(await eapi({action:'deldoc',id,title}))paint(true)}}
"""

GONE = '<div id="gone" class="card" style="display:none"></div>'
DOC_EDIT = ('<details class="ed"><summary>编辑</summary><div class="bar"><button class="cb" id="edDel">删除这篇</button></div>'
            '<div class="meta">删除后网页上立刻看不到，可以撤销；Mac 下次发布时把本机那份挪进回收站。</div></details>')
TASK_EDIT = ('<details class="ed"><summary>编辑</summary><div class="bar"><button class="cb" id="edDelT">删除这条任务记录</button></div>'
             '<div class="meta">只删这条记录，不动文稿。</div></details>')

CLOUD_JS = r"""
const CP='zx-cloud-pass';
function cget(){try{return localStorage.getItem(CP)||''}catch(e){return ''}}
function cset(p){try{p?localStorage.setItem(CP,p):localStorage.removeItem(CP)}catch(e){}}
async function capi(b){const r=await fetch('/api/cloud',{method:'POST',
 headers:{'content-type':'application/json'},body:JSON.stringify(b)});
 try{return await r.json()}catch(e){return {error:'http_'+r.status,msg:'服务出错（'+r.status+'）'}}}
function csay(h){document.getElementById('cs').innerHTML=h}
function cbtn(d){document.querySelectorAll('.cb').forEach(b=>b.disabled=d)}
async function cgo(mode){
 const url=document.getElementById('cu').value.trim();
 if(!/bilibili\.com|b23\.tv|bili2233\.cn|BV[0-9A-Za-z]{10}/.test(url)){csay('先粘贴 B站 视频链接');return}
 const pass=cget()||prompt('云端转写口令（装机时生成的那串，每台设备输一次）')||'';
 if(!pass)return;
 cbtn(true);
 try{
  if(mode==='Y'){
   csay('解析中…');
   const j=await capi({url,mode:'info',pass});
   if(j.error==='bad_pass'){cset('');csay('口令不对，再点一次重新输入');return}
   if(j.error){csay(esc(j.msg||j.error));return}
   cset(pass);
   const m=j.meta;
   if(!confirm('《'+m.title+'》\n'+m.up+' · '+Math.max(1,Math.round(m.dur/60))+' 分钟\n精修约 '+j.cost+' 元，确定？')){csay('');return}
  }
  csay('提交中…');
  const j=await capi({url,mode,pass});
  if(j.error==='bad_pass'){cset('');csay('口令不对，再点一次重新输入');return}
  if(j.task){cset(pass);location.href='/t.html?id='+encodeURIComponent(j.task);return}
  csay(esc(j.msg||j.error||'出错了'));
 }catch(e){csay('出错：'+esc(String(e)))}finally{cbtn(false)}
}
document.querySelectorAll('.cb').forEach(b=>b.onclick=()=>cgo(b.dataset.m));
async function loadCloud(){
 const v=await loadNew();if(!v.length)return;
 ALL.unshift(...v);
 document.getElementById('recent').insertAdjacentHTML('afterbegin',
  v.map(d=>cardHTML(d).replace('</span></a>',' · 入库 '+d.a+'</span></a>')).join(''));
 paintAll();}
function hm(t){const d=new Date(t),p=n=>String(n).padStart(2,'0');return p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes())}
async function loadTasks(){
 try{const j=await (await fetch('/api/cloud?tasks&_='+Date.now())).json();
  const v=(j.tasks||[]).slice(0,5);if(!v.length)return;
  const ic={done:'✓',error:'✗',running:'⏳'};
  document.getElementById('tasks').innerHTML='<div class="sec">最近任务</div>'+v.map(t=>{
   const bad=(t.steps||[]).find(s=>s.s==='fail');
   const tail=t.status==='error'?'<div class="meta" style="color:var(--accent)">卡在「'+esc(bad?bad.name:'')+'」：'+esc(t.reason||'')+'</div>':'';
   return '<a class="card" href="/t.html?id='+encodeURIComponent(t.id)+'"><span class="meta">'+ic[t.status]+' '+hm(t.t0)+' · '+
    (t.src==='mac'?'Mac':'网页云端')+' · '+({Y:'Y 精修',T:'T 免费',U:'整理稿'}[t.mode]||t.mode)+'</span><b>'+esc(t.title||t.url||'')+'</b>'+tail+'</a>'}).join('');
 }catch(e){}}
loadCloud();loadTasks();
"""

HL_JS = r"""<script>
const E=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function draw(){const g=[];for(const k in W){const hs=(W[k].hl||[]).filter(h=>!h.del);if(hs.length)g.push([k,hs])}
 g.sort((a,b)=>Math.max(...b[1].map(h=>h.t))-Math.max(...a[1].map(h=>h.t)));
 document.getElementById('hn').textContent=g.reduce((s,x)=>s+x[1].length,0)+' 条划线 · '+g.length+' 篇文稿';
 document.getElementById('hl').innerHTML=g.length?g.map(([k,hs])=>'<h2><a href="'+E(hs[0].u||'/d/'+k+'.html')+'">'+E(hs[0].d||k)+'</a></h2>'+
  hs.sort((a,b)=>b.t-a.t).map(h=>'<div class="card"><b style="font-weight:400">'+E(h.q)+'</b>'+(h.n?'<span class="meta">笔记：'+E(h.n)+'</span>':'')+'</div>').join('')).join('')
  :'<div class="empty">还没有划线。在阅读页选中一段文字，点「划线」。</div>'}
lload();draw();pull().then(draw);
</script>"""


T_JS = r"""<script>
const ID=new URLSearchParams(location.search).get('id')||'';
const E=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const IC={ok:'✓',fail:'✗',run:'⏳',skip:'–',wait:'·'};
const sec=ms=>ms==null?'':(ms<1000?'<1 秒':Math.round(ms/1000)+' 秒');
let readHref=null;
async function href(bv){if(readHref)return readHref;
 try{const r=await fetch('/d/'+bv.toLowerCase()+'.html',{method:'HEAD'});readHref=r.ok?'/d/'+bv.toLowerCase()+'.html':'/c.html?bv='+bv}
 catch(e){readHref='/c.html?bv='+bv}return readHref}
async function load(){
 const box=document.getElementById('task');
 if(!/^[\w-]{6,60}$/.test(ID)){box.innerHTML='<div class="empty">任务号不对</div>';return}
 let t;try{const r=await fetch('/api/cloud?task='+ID+'&_='+Date.now());if(!r.ok)throw 0;t=await r.json()}
 catch(e){box.innerHTML='<div class="empty">找不到这个任务</div>';return}
 const st={done:'✓ '+(t.outcome||'已出稿'),error:'✗ 没成功',running:'⏳ 进行中'}[t.status];
 const used=Math.round(((t.status==='running'?Date.now():t.t)-t.t0)/1000);
 let h='<h1>'+st+'</h1><div class="meta">'+E(t.title||t.url)+'<br>'+(t.src==='mac'?'Mac':'网页云端')+' · '+
  ({Y:'Y 精修',T:'T 免费',U:'整理稿同步'}[t.mode]||t.mode)+' · '+new Date(t.t0).toLocaleString('zh-CN',{hour12:false})+' · 用时 '+used+' 秒</div>';
 if(t.status==='error'){
  const bad=(t.steps||[]).find(s=>s.s==='fail');
  h+='<div class="card" style="border-color:var(--accent)"><b>卡在「'+E(bad?bad.name:'')+'」</b>'+
   '<p style="margin:.4rem 0 .2rem"><b>原因：</b>'+E(t.reason)+'</p><p style="margin:0"><b>怎么办：</b>'+E(t.fix)+'</p></div>';
 }
 if(t.status==='done'){
  const bits=[t.chars?t.chars+' 字':'',t.cost?'花费约 '+t.cost+' 元':'',t.unresolved?'待核 '+t.unresolved+' 项':'',t.note||''].filter(Boolean);
  h+='<div class="card">'+(t.bvid?'<a href="'+(await href(t.bvid))+'"><b>阅读全文 →</b></a>':'')+
   (bits.length?'<span class="meta">'+E(bits.join(' · '))+'</span>':'')+'</div>';
 }
 h+='<table>'+(t.steps||[]).map(s=>'<tr><td>'+IC[s.s]+'</td><td>'+E(s.name)+'</td><td>'+
  E(s.note||'')+'</td><td>'+(s.s==='run'?'进行中':sec(s.ms))+'</td></tr>').join('')+'</table>';
 if(t.msg&&t.status==='error')h+='<details><summary class="meta">技术细节</summary><pre style="white-space:pre-wrap;font-size:.75rem">'+E(t.msg)+'</pre></details>';
 box.innerHTML=h;
 if(t.status==='running')setTimeout(load,2500);
}
load();
document.getElementById('edDelT').onclick=async()=>{if(!confirm('删除这条任务记录？（不动文稿）'))return;
 if(await eapi({action:'deltask',id:ID}))location.href='/'};
</script>"""


C_JS = r"""<script>
const BV=new URLSearchParams(location.search).get('bv')||'';
const E=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const DUR=s=>s>=3600?Math.floor(s/3600)+'h'+Math.floor(s%3600/60)+'m':Math.floor(s/60)+'m'+(s%60)+'s';
const LG=p=>{const c=(p.match(/[一-鿿]/g)||[]).length;return c>0.3*Math.max(1,p.replace(/\s/g,'').length)?'zh':'en'};
(async()=>{const box=document.getElementById('doc');
 if(!/^(BV[0-9A-Za-z]{10}|M\d{8}-[0-9a-f]{4,8})$/.test(BV)){box.innerHTML='<div class="empty">链接不对</div>';return}
 try{const r=await fetch('/api/cloud?doc='+BV+'&_='+Date.now());if(!r.ok)throw new Error(r.status);
  const d=await r.json();document.title=d.title;
  const man=d.mode==='M';
  const tag=man?'整理稿':d.mode==='T'?'快车道·可能有缺失':'';     // 和正式文稿同一套标签
  const link=man?(d.url?'<a href="'+E(d.url)+'">打开原文</a>':'')+(d.note?'<br>'+E(d.note):'')+(d.source?'<br>'+E(d.source):'')
   :'<a href="https://www.bilibili.com/video/'+BV+'/">在 B站 打开原视频</a>';
  const ps=d.text.split('\n\n').map(p=>p.trim()).filter(Boolean),lg=ps.map(LG),both=lg.includes('en')&&lg.includes('zh');
  box.innerHTML='<h1>'+E(d.title)+'</h1><div class="meta">'+E(d.up)+' · '+E(d.pub)+(d.dur?' · '+DUR(d.dur):'')+' · '+
   d.chars+' 字'+(tag?'<span class="tag">'+tag+'</span>':'')+'<br>'+link+'</div><hr style="border:0;border-top:1px solid var(--line);margin:1.2rem 0">'+
   ps.map((p,i)=>{const m=p.match(/^\*\*(.+?)\*\*：([\s\S]*)$/);
    return m?'<p class="t"><i>'+E(m[1])+'</i>'+E(m[2])+'</p>':'<p'+(both?' class="'+lg[i]+'"':'')+'>'+E(p)+'</p>'}).join('');
  initDocEdit(BV,d.title);
  // 收藏星：和正式文稿同一套权重（按小写编号记），发布成正式页后接着用
  const K=BV.toLowerCase(),hd=document.querySelector('header .wrap');
  hd.insertAdjacentHTML('beforeend','<span class="num rnum"></span><span class="imp" data-bv="'+K+'"></span>');
  const nm=hd.querySelector('.rnum');
  function paintW(){const o=W[K]||{},n=nOf(o);paintImp(paintW);nm.textContent=n?fmt(o):'';nm.className='rnum'+(n>=FAVN?' on':'')}
  lload();paintW();open1(K);pull().then(paintW);typeBar(box.querySelector('.meta'));initReader(K,box);
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
