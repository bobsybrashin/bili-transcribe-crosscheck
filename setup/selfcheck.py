#!/usr/bin/env python3
"""安装后自检：按热键会走的两条链路各真跑一遍关键环节，不写文稿、不动站点。

  T（免费）：解析链接 → 取平台字幕轨（验 B站 cookie）
  Y（精修）：解析链接 → yt-dlp 下音频（验 Chrome 登录态）→ 切 3 秒送豆包识别（验 API Key，花费约 0.0007 元）
  网页备用入口：/api/cloud 在线、云端密钥已配（用一个错误口令试，应被拒）
  热键环境：hotkey.sh 用的精简 PATH 下 node / yt-dlp / ffmpeg / netlify 都找得到，~/.zshenv 里两个变量都在

用法：selfcheck.py <库根目录>；全过退出 0
"""
import os, sys, pathlib, tempfile, subprocess, shutil

ROOT = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'src'))
FAST_URL = 'https://www.bilibili.com/video/BV1QreX69Ezz/'   # 有中文 AI 字幕轨（铁牛jia，2 分半）
FINE_URL = 'https://www.bilibili.com/video/BV1bJxF6SEye/'   # 1 分 47 秒，没有字幕轨，只能精修
HOTKEY_PATH = f'/opt/homebrew/bin:{pathlib.Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'

CI = os.environ.get('ZX_CI') == '1'      # 无人值守：缺凭据的项标「跳过」，不算失败

class Skip(Exception):
    pass

bad = []
def check(name, fn):
    try:
        msg = fn()
        print(f'  ✓ {name}' + (f'：{msg}' if msg else ''), flush=True)
    except Skip as e:
        print(f'  · {name}：跳过（{e}）', flush=True)
    except Exception as e:
        bad.append(name)
        print(f'  ✗ {name}：{str(e).splitlines()[0][:160]}', flush=True)

def hotkey_env():
    env = subprocess.run(['/bin/zsh', '-c', 'echo ${VOLC_SPEECH_API_KEY:+V}${SITE_WRITE_KEY:+S}'],
                         capture_output=True, text=True, env={'HOME': str(pathlib.Path.home()), 'PATH': HOTKEY_PATH}).stdout.strip()
    miss = [t for t in ('node', 'yt-dlp', 'ffmpeg', 'netlify', 'python3') if not shutil.which(t, path=HOTKEY_PATH)]
    if miss: raise RuntimeError('热键环境里找不到 ' + '、'.join(miss))
    if 'V' not in env and not CI: raise RuntimeError('~/.zshenv 里没有 VOLC_SPEECH_API_KEY，热键读不到')
    if 'S' not in env: raise RuntimeError('~/.zshenv 里没有 SITE_WRITE_KEY，部署会变只读站')
    if not os.access(ROOT / 'src' / 'hotkey.sh', os.X_OK): raise RuntimeError('src/hotkey.sh 没有执行权限')

def t_lane():
    if CI and not (pathlib.Path.home() / '.config/transcribe/bilibili-cookie.json').exists():
        raise Skip('没给 B站 cookie')
    import fetch
    meta = fetch.resolve(FAST_URL)
    lan, body = fetch.subtitle(meta)
    if not body: raise RuntimeError('字幕轨为空：B站 cookie 失效，跑 setup/refresh-cookie.sh')
    return f'《{meta["title"][:16]}…》字幕 {len(body)} 句'

def y_lane():
    if CI and not os.environ.get('VOLC_SPEECH_API_KEY'):
        raise Skip('没给豆包 API Key')
    import fetch, asr
    meta = fetch.resolve(FINE_URL)
    with tempfile.TemporaryDirectory() as tmp:
        full = fetch.audio(meta, tmp)
        piece = fetch.slice_audio(full, pathlib.Path(tmp) / 'probe.mp3', 30, 3)
        u = asr.recognize(piece, log=lambda *a: None, tries=1)
    return f'下载音频 + 豆包识别 3 秒片段 → {len(u)} 句'

def cloud():
    import json, urllib.request, urllib.error
    site = 'https://zhuanxieku.netlify.app'
    n = len(json.loads(urllib.request.urlopen(site + '/api/cloud?list', timeout=30).read()).get('docs', []))
    req = urllib.request.Request(site + '/api/cloud', headers={'content-type': 'application/json'},
                                 data=json.dumps({'mode': 'info', 'url': 'BV1QreX69Ezz', 'pass': 'selfcheck-wrong'}).encode())
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 401: return f'在线，密钥已配（云端稿 {n} 篇）'
        if e.code == 503: raise RuntimeError('云端密钥没配：跑 setup/cloud-secrets.sh')
        raise RuntimeError(f'入口异常 HTTP {e.code}')
    raise RuntimeError('错误口令居然通过了')

check('热键环境', hotkey_env)
check('T 免费链路', t_lane)
check('Y 精修链路', y_lane)
check('网页云端备用入口', cloud)
sys.exit(1 if bad else 0)
