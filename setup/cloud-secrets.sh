#!/bin/zsh
# 把云端转写（网页备用入口）要用的密钥放进 Netlify Blobs 私有存储 zhuanxie-secrets/all：
#   B站 登录态（bilibili-cookie.json）、豆包 API Key（~/.zshenv）、网页口令的 SHA-256。
# 函数运行时现读，改了不用重新部署。refresh-cookie.sh 刷新 cookie 后会自动再跑本脚本。
# 网页口令第一次自动生成，存在 ~/.config/transcribe/cloud-pass，之后沿用。不打印任何密钥，只打印口令。
set -u
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
ROOT=${ZX_ROOT:-${0:A:h:h}}; CFG=$HOME/.config/transcribe; PASSF=$CFG/cloud-pass
tmo() { perl -e 'alarm shift; exec @ARGV' "$@" }
[[ -f $ROOT/.netlify/state.json ]] || { echo "✗ $ROOT 还没关联 Netlify 站点"; exit 1 }
[[ -f $CFG/bilibili-cookie.json ]] || { echo "✗ 没有 B站 cookie：先跑 refresh-cookie.sh"; exit 1 }
[[ -n ${VOLC_SPEECH_API_KEY:-} ]] || source $HOME/.zshenv 2>/dev/null
[[ -n ${VOLC_SPEECH_API_KEY:-} ]] || { echo "✗ ~/.zshenv 里没有 VOLC_SPEECH_API_KEY"; exit 1 }
export VOLC_SPEECH_API_KEY
[[ -s $PASSF ]] || ( umask 077; LC_ALL=C tr -dc 'abcdefghjkmnpqrstuvwxyz23456789' </dev/urandom | head -c 8 > $PASSF )

T=$(mktemp -d); trap 'rm -rf $T' EXIT; chmod 700 $T
python3 - $CFG/bilibili-cookie.json $PASSF $T/all.json <<'PY'
import sys, json, os, hashlib, time
ck = json.load(open(sys.argv[1])); pw = open(sys.argv[2]).read().strip()
fd = os.open(sys.argv[3], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    json.dump({'bili': {k: ck[k] for k in ('sessdata', 'bili_jct', 'dede_user_id')},
               'volc': os.environ['VOLC_SPEECH_API_KEY'],
               'pass_sha256': hashlib.sha256(pw.encode()).hexdigest(), 'at': int(time.time())}, f)
PY
cd $ROOT
tmo 120 netlify blobs:set zhuanxie-secrets all --input $T/all.json </dev/null >/dev/null 2>&1
tmo 120 netlify blobs:get zhuanxie-secrets all --output $T/back.json </dev/null >/dev/null 2>&1
cmp -s $T/all.json $T/back.json || { echo "✗ 云端密钥没写进去（netlify blobs:set 失败），再跑一次"; exit 1 }
echo "  ✓ 云端转写密钥已就位。网页口令：$(cat $PASSF)（每台设备第一次用时输入一次）"
