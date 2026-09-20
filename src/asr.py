#!/usr/bin/env python3
"""豆包录音文件识别 2.0 封装。资源 ID 是 volc.seedasr.auc（不是文档写的 bigasr）。"""
import os, json, uuid, time, base64, pathlib, urllib.request, urllib.error

URL = 'https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash'
RESOURCE = 'volc.seedasr.auc'
SEG, OV = 3600, 60          # flash 上限 2h，取 1h 一段留足余量；重叠 60s 供说话人对齐
MAX_MB = 90

def _key():
    k = os.environ.get('VOLC_SPEECH_API_KEY')
    if not k:
        raise RuntimeError('缺少环境变量 VOLC_SPEECH_API_KEY —— '
                           '在火山引擎控制台「语音技术 → 录音文件识别」里拿')
    return k

def spans(total):
    n = (total + SEG - 1) // SEG
    return [(max(0, i * SEG - OV), min(total, (i + 1) * SEG)) for i in range(n)]

def cut(i, n):
    """段 i 保留的绝对时间区间，两侧用同一条线，避免接缝重复"""
    return (-1 if i == 0 else i * SEG - OV / 2,
            (i + 1) * SEG - OV / 2 if i < n - 1 else float('inf'))

def recognize(mp3, hotwords=(), speaker_info=True, tries=3, log=print):
    data = base64.b64encode(pathlib.Path(mp3).read_bytes()).decode()
    mb = len(data) / 1048576
    if mb > MAX_MB: raise RuntimeError(f'{mp3} base64 {mb:.0f}MB 超过 {MAX_MB}MB')
    req = {'model_name': 'bigmodel', 'enable_punc': True, 'enable_itn': True,
           'enable_ddc': True, 'enable_speaker_info': bool(speaker_info)}
    if hotwords:
        req['corpus'] = {'context': json.dumps(
            {'hotwords': [{'word': w} for w in hotwords]}, ensure_ascii=False)}
    body = json.dumps({'user': {'uid': 'transcribe'},
                       'audio': {'data': data}, 'request': req}).encode()
    h = {'X-Api-Key': _key(), 'X-Api-Resource-Id': RESOURCE, 'X-Api-Sequence': '-1',
         'X-Api-Request-Id': str(uuid.uuid4()), 'Content-Type': 'application/json'}
    last = None
    for k in range(tries):
        t0 = time.time()
        try:
            r = urllib.request.urlopen(urllib.request.Request(URL, body, h), timeout=1200)
            sc = r.headers.get('X-Api-Status-Code')
            if sc != '20000000':
                raise RuntimeError(f'{sc} {r.headers.get("X-Api-Message")}')
            u = json.loads(r.read())['result']['utterances']
            log(f'      {pathlib.Path(mp3).name} → {len(u)} 句 / {time.time()-t0:.0f}s')
            return u
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code} {e.headers.get("X-Api-Status-Code")} {e.headers.get("X-Api-Message")}'
        except Exception as e:
            last = str(e)
        log(f'      第 {k+1} 次失败: {last}')
        if k < tries - 1: time.sleep(5 * (k + 1))
    raise RuntimeError(last)
