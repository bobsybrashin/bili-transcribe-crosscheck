#!/bin/zsh
# 从 Chrome 读 B站 登录态，写成转写库要的 ~/.config/transcribe/bilibili-cookie.json。不打印任何 cookie 值。
# Chrome 的 cookie 用钥匙串里的密钥加密：第一次会弹钥匙串窗口，输入这台 Mac 的登录密码并点「始终允许」，
# 以后就不再问（只点「允许」的话，每次都会再弹）。
# cookie 约一个月过期；转写报「没有中文字幕轨」或自检说字幕轨为空时，再跑一次即可：
#   ~/Documents/转写库/setup/refresh-cookie.sh
set -u
HERE=${0:A:h}
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
D="$HOME/.config/transcribe"; C="$HOME/Library/Application Support/Google/Chrome"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$D"; chmod 700 "$D"

# 1. 先看 Chrome 哪个用户资料里有 B站 登录 cookie（只数条数，不读值，不需要钥匙串）
PROF=""
for p in "$C"/Default "$C"/Profile*(N); do
  [ -f "$p/Cookies" ] || continue
  cp "$p/Cookies" "$T/c.db" 2>/dev/null || continue
  n=$(sqlite3 "$T/c.db" "select count(*) from cookies where host_key like '%bilibili.com' and name in ('SESSDATA','bili_jct','DedeUserID');" 2>/dev/null)
  [ "${n:-0}" -ge 3 ] && { PROF="${p:t}"; break; }
done
[ -n "$PROF" ] || { echo "✗ Chrome 里没有 B站 登录：先在 Chrome 打开 bilibili.com 登录，再跑一次"; exit 1; }

# 2. 让 yt-dlp 解密（会用钥匙串）。钥匙串弹窗可能要几秒才被点掉，所以最多试 4 次
for i in 1 2 3 4; do
  rm -f "$T/jar.txt"
  yt-dlp --cookies-from-browser "chrome:$PROF" --cookies "$T/jar.txt" --simulate --quiet --no-warnings \
    "https://www.bilibili.com/video/BV1GJ411x7h7/" </dev/null >/dev/null 2>&1
  # 成功后：云端备用入口配过的话，顺手把新 cookie 同步到云端
  python3 - "$T/jar.txt" "$D/bilibili-cookie.json" <<'PY' && { [ -s "$D/cloud-pass" ] && "$HERE/cloud-secrets.sh"; exit 0; }
import sys, json, os, datetime, urllib.request
want = {'SESSDATA': 'sessdata', 'bili_jct': 'bili_jct', 'DedeUserID': 'dede_user_id'}
got, exp = {}, None
try:
    lines = open(sys.argv[1], encoding='utf-8', errors='replace').read().splitlines()
except FileNotFoundError:
    sys.exit(3)
for line in lines:
    if line.startswith('#HttpOnly_'): line = line[len('#HttpOnly_'):]
    elif line.startswith('#') or not line.strip(): continue
    f = line.split('\t')
    if len(f) == 7 and f[0].endswith('bilibili.com') and f[5] in want and f[6]:
        got[want[f[5]]] = f[6]
        if f[5] == 'SESSDATA' and f[4].isdigit(): exp = int(f[4])
if len(got) < 3:
    sys.exit(3)                                    # 解密没成功：钥匙串没放行
ck = '; '.join(f'{k}={got[v]}' for k, v in (('SESSDATA', 'sessdata'), ('bili_jct', 'bili_jct'), ('DedeUserID', 'dede_user_id')))
req = urllib.request.Request('https://api.bilibili.com/x/web-interface/nav',
                             headers={'Cookie': ck, 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'})
if not json.loads(urllib.request.urlopen(req, timeout=15).read()).get('data', {}).get('isLogin'):
    print('✗ Chrome 里的 B站 登录已失效：在 Chrome 重新登录 bilibili.com，再跑一次'); sys.exit(4)
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as fh: json.dump(got, fh, indent=2)
if exp and exp > 1e14: exp = exp / 1e6 - 11644473600   # Chrome 时间：1601 年起的微秒
elif exp and exp > 1e11: exp = exp / 1e3
try: until = datetime.date.fromtimestamp(exp).isoformat() if exp else '未知'
except (ValueError, OverflowError, OSError): until = '未知'
print(f'  ✓ B站 登录态已写入（{os.path.basename(sys.argv[2])}，过期日 {until}）')
PY
  [ $? -eq 4 ] && exit 1
  [ $i -lt 4 ] && { echo "  · 等钥匙串放行：弹窗里输入 Mac 登录密码，点「始终允许」（第 $i 次，5 秒后重试）"; sleep 5; }
done
echo "✗ 钥匙串一直没放行，读不了 Chrome 的 cookie：弹窗里输入 Mac 登录密码并点「始终允许」，再跑一次"
exit 1
