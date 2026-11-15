#!/usr/bin/env python3
"""一次转写任务（热键调用它）：分步记录，结束时给一个看得见、不会自己消失的结果。

  task.py T|Y <链接>

· 每一步记 ✓/✗/耗时，写进 .work/tasks/<id>.json，并同步到站点——首页「最近任务」、任务页 t.html 都看得到，手机也能看
· 出完稿立刻放上站点「新稿」区：手机马上能读，不用发布、不花额度；下次发布时自动变成正式文稿
· 结束时弹一条通知，并打开任务页：成功写标题、时长、花费、待核项；失败写卡在哪一步、原因、怎么办
  站点连不上时，任务页换成本机的 .work/tasks/<id>.html
退出码沿用 ts.py：0 成功，2 没有中文字幕，3 已有精修版，其他为失败。
流水线本身（ts.py）不改：这里只是在它调用的几个函数外面包一层记步骤。
"""
import os, re, sys, json, time, html, argparse, pathlib, subprocess, traceback, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ts, fetch, asr

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASKS = ROOT / '.work' / 'tasks'
SITE = os.environ.get('ZX_SITE', 'https://zhuanxieku.netlify.app')
PASSF = pathlib.Path.home() / '.config/transcribe/cloud-pass'
PRICE = 0.8
STEPS = {
    'T': [('link', '读链接'), ('meta', '解析视频'), ('sub', '取字幕'), ('write', '写文稿'), ('upload', '放上网站')],
    'Y': [('link', '读链接'), ('meta', '解析视频'), ('audio', '下载音频'), ('asr', '豆包识别'),
          ('check', '双源核对'), ('write', '写文稿'), ('upload', '放上网站')],
}
# 失败原因 → 白话原因 + 一句怎么办（站点端 netlify/lib/cloud.mjs 里有同一张表的 JS 版）
RULES = [
    (r'找不到 B站 cookie|bilibili-cookie|缺少字段', 'B站 登录态没配好', '跑 ~/Documents/转写库/setup/refresh-cookie.sh'),
    (r'VOLC_SPEECH_API_KEY', '没配豆包 API Key', '重跑那一行安装命令，第 ③ 问填 Key'),
    (r'4500\d{4}|X-Api|HTTP 40[13]', '豆包拒绝了请求（Key 无效、没开通或余额不足）', '去火山引擎控制台看 API Key 和余额'),
    (r'yt-dlp|音频下载失败', '音频下载失败', '再按一次；还不行在终端跑 brew upgrade yt-dlp'),
    (r'ffmpeg', '音频转码失败', '在终端跑 brew reinstall ffmpeg'),
    (r'无法从链接中识别|没认出', '没认出 B站 视频链接', '复制视频页的地址再按（番剧要用 ep/ss 链接）'),
    (r'NotImplementedError|YouTube|视频号', '这类链接还不支持', '目前只支持 B站'),
    (r'pagelist|412|风控|-352', 'B站 接口拒绝了请求', '过几分钟再试；老出现就跑 refresh-cookie.sh'),
    (r'timed out|URLError|Connection|getaddrinfo|SSL|Network|reset by peer', '网络不通或超时',
     '再按一次（做完的步骤会复用，不重复扣费）'),
]


def explain(msg):
    for pat, reason, fix in RULES:
        if re.search(pat, msg):
            return reason, fix
    return '没预料到的错误：' + msg.strip().splitlines()[-1][:80], '再按一次；还不行把任务页截图发给 Claude'


ms = lambda: int(time.time() * 1000)


def post(body, timeout=8):
    req = urllib.request.Request(SITE + '/api/cloud', data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={'content-type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


class Task:
    def __init__(self, mode, url):
        self.d = {'id': f'{ms():x}-{os.urandom(2).hex()}', 'src': 'mac', 'mode': mode, 'url': url[:300],
                  'status': 'running', 't0': ms(), 't': ms(),
                  'steps': [{'k': k, 'name': n, 's': 'wait'} for k, n in STEPS[mode]]}
        self.pw = PASSF.read_text().strip() if PASSF.exists() else ''
        self.synced = False                     # 站点那边有没有收到过这份记录
        self.offline = not self.pw

    def step(self, k):
        return next((s for s in self.d['steps'] if s['k'] == k), None)

    def running(self):
        return next((s for s in self.d['steps'] if s['s'] == 'run'), None)

    def _close(self):
        s = self.running()
        if s:
            s['s'], s['ms'] = 'ok', ms() - s['t0']

    def enter(self, k, note=None):
        s = self.step(k)
        if not s or s['s'] in ('run', 'ok'):    # 分段识别会多次进同一步，只记一次
            return
        self._close()
        for x in self.d['steps']:               # 前面没走过的步骤 = 复用了上次的结果
            if x is s:
                break
            if x['s'] == 'wait':
                x['s'], x['note'] = 'skip', '复用上次的结果，没再扣费' if x['k'] in ('audio', 'asr') else '跳过'
        s['s'], s['t0'] = 'run', ms()
        if note:
            s['note'] = note
        self.save()

    def done(self, **extra):
        self._close()
        for s in self.d['steps']:
            if s['s'] == 'wait':
                s['s'] = 'skip'
        self.d.update(extra, status='done')
        self.save(final=True)

    def fail(self, msg, reason=None, fix=None):
        s = self.running() or next((x for x in self.d['steps'] if x['s'] == 'wait'), None)
        if s:
            s['s'] = 'fail'
            if 't0' in s:
                s['ms'] = ms() - s['t0']
        r, f = explain(msg)
        self.d.update(status='error', reason=reason or r, fix=fix or f, msg=msg.strip()[-300:])
        self.save(final=True)

    def save(self, final=False):
        self.d['t'] = ms()
        TASKS.mkdir(parents=True, exist_ok=True)
        (TASKS / f"{self.d['id']}.json").write_text(json.dumps(self.d, ensure_ascii=False, indent=1), encoding='utf-8')
        if self.offline and not final:
            return
        try:
            post({'action': 'task', 'task': self.d, 'pass': self.pw}, timeout=10 if final else 6)
            self.synced, self.offline = True, False
        except Exception:
            self.offline = True                 # 连不上就先不再试，最后一次再试


def hook(mod, name, key):
    f = getattr(mod, name)

    def g(*a, **k):
        T.enter(key(*a, **k) if callable(key) else key)
        return f(*a, **k)
    setattr(mod, name, g)


def read_doc(p):
    t = p.read_text(encoding='utf-8')
    fm_s, body = re.match(r'---\n(.*?)\n---\n+(.*)', t, re.S).groups()
    fm = dict(l.split(': ', 1) for l in fm_s.splitlines() if ': ' in l)
    return fm, body.strip()


def secs(d):
    m = re.match(r'(?:(\d+)h)?(\d+)m(?:(\d+)s)?', d or '')
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0) if m else 0


def local_page(d):
    """站点连不上时的本机任务页"""
    icon = {'ok': '✓', 'fail': '✗', 'run': '…', 'skip': '–', 'wait': '·'}
    rows = ''.join(f"<tr><td>{icon[s['s']]}</td><td>{html.escape(s['name'])}</td>"
                   f"<td>{html.escape(s.get('note', ''))}</td></tr>" for s in d['steps'])
    if d['status'] == 'error':
        box = f"<h2>✗ 卡在这一步</h2><p><b>原因：</b>{html.escape(d['reason'])}</p><p><b>怎么办：</b>{html.escape(d['fix'])}</p>"
    else:
        box = (f"<h2>✓ {html.escape(d.get('outcome', '已出稿'))}</h2><p>{html.escape(d.get('title', ''))}</p>"
               f"<p>{html.escape(d.get('note', ''))}</p><p>{html.escape(d.get('path', ''))}</p>")
    p = TASKS / f"{d['id']}.html"
    p.write_text(f'<!doctype html><meta charset="utf-8"><title>转写任务</title><body style="font:16px/1.7 -apple-system;'
                 f'max-width:40rem;margin:2rem auto;padding:0 1rem">{box}<table>{rows}</table>'
                 f'<p style="color:#888">站点暂时连不上，这是本机记录：{html.escape(str(p))}</p></body>', encoding='utf-8')
    return p


def notify(title, body):
    if os.environ.get('ZX_QUIET'):
        return
    q = lambda s: s.replace('\\', '\\\\').replace('"', '\\"')
    subprocess.run(['osascript', '-e', f'display notification "{q(body)}" with title "转写" subtitle "{q(title)}"'],
                   capture_output=True)


def run(mode, url):
    T.enter('link')
    if not re.search(r'bilibili\.com|b23\.tv|bili2233\.cn|BV[0-9A-Za-z]{10}', url):
        return T.fail('剪贴板里不是 B站 链接', '剪贴板里不是 B站 视频链接', '先复制视频链接，再按快捷键') or 1
    a = argparse.Namespace(fine=(mode == 'Y'), fast=(mode == 'T'), no_check=False, review=None, finalize=None,
                           speakers=None, solo=False, all=False, yes=False)   # 批量精修不经确认绝不花钱
    T.enter('meta')
    exp = fetch.expand(url)
    if exp:                                     # 合集 / UP 主空间：整批跑，只记总结果
        T.d.update(title=f'{exp[0]}《{exp[1]}》{len(exp[2])} 条')
        code = ts.run_batch(*exp, a)
        if code == 0:
            T.done(note='批量完成，新稿下次发布时上网站')
        elif code == 4:
            T.fail('批量精修未确认', '批量精修要先确认花费', '在终端跑 bin/ts.py <链接> --fine --yes')
        else:
            T.fail(f'批量退出码 {code}', '批量里有条目失败', '看 .work/hotkey.log 里标 ✗ 的那几条，单独再按一次')
        return code
    meta = fetch.resolve(url)
    T.d.update(bvid=meta['bvid'], title=meta['title'], up=meta.get('up'), dur=meta['dur'])
    T.save()
    code, path = ts.run_one(meta, a)
    if code == 2:
        T.fail('无中文字幕轨', '这条视频没有中文字幕，免费模式出不了稿', '改按 ⌃⌘Y 走精修')
        return code
    if code == 3:
        T.done(outcome='已有精修版，没重出', note='免费模式不覆盖精修版；要重出用 ⌃⌘Y')
        return code
    fm, body = read_doc(path)
    paid = T.step('audio') and T.step('audio')['s'] in ('run', 'ok')
    extra = {'chars': int(fm.get('chars') or 0), 'path': str(path.relative_to(ROOT)),
             'cost': round(meta['dur'] / 3600 * PRICE, 2) if paid else 0}
    if fm.get('unresolved'):
        extra['unresolved'] = int(fm['unresolved'])
    T.enter('upload')
    try:
        if not T.pw:
            raise RuntimeError('没有云端口令（~/.config/transcribe/cloud-pass）')
        post({'action': 'putdoc', 'pass': T.pw, 'doc': {
            'bvid': meta['bvid'], 'title': fm.get('title'), 'up': fm.get('up', ''), 'pub': fm.get('published', ''),
            'dur': secs(fm.get('duration')), 'mode': mode, 'source': fm.get('source', ''),
            'chars': extra['chars'], 'text': body}}, timeout=20)
    except Exception as e:
        s = T.step('upload')
        s.update(s='fail', note=f'没放上网站（{str(e)[:60]}），稿子在本机')
        T.done(**extra)
        return 0
    T.done(**extra)
    return 0


if __name__ == '__main__':
    mode, url = sys.argv[1].upper(), (sys.argv[2] if len(sys.argv) > 2 else '').strip()
    T = Task(mode, url)
    hook(fetch, 'subtitle', lambda *a, **k: 'sub' if mode == 'T' else 'check')
    hook(fetch, 'audio', 'audio')
    hook(asr, 'recognize', 'asr')
    hook(ts, 'write', 'write')
    try:
        code = run(mode, url)
    except BaseException as e:
        msg = ''.join(traceback.format_exception_only(type(e), e))
        traceback.print_exc()
        T.fail(msg)
        code = 1
    d = T.d
    up = next((s for s in d['steps'] if s['k'] == 'upload'), {})
    if d['status'] == 'done':
        title = d.get('title') or ''
        tail = '' if up.get('s') != 'fail' else ' · 网站上暂时看不到'
        notify(f"✓ {d.get('outcome', '已出稿')}{tail}", f"《{title[:40]}》" + (f" · {d['chars']} 字" if d.get('chars') else ''))
    else:
        bad = next((s['name'] for s in d['steps'] if s['s'] == 'fail'), '')
        notify(f'✗ 卡在「{bad}」', f"{d['reason']} → {d['fix']}")
    target = f"{SITE}/t.html?id={d['id']}" if T.synced else str(local_page(d))
    if not os.environ.get('ZX_QUIET'):        # 测试时不弹通知、不开页面
        subprocess.run(['open', target], capture_output=True)
    print(f"  任务页：{target}")
    sys.exit(code)
