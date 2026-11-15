#!/bin/zsh
# 转写库 · 一步安装
#
#   zsh -c "$(curl -fsSL https://raw.githubusercontent.com/bobsybrashin/bili-transcribe-crosscheck/main/install.sh)"
#
# 第 1 步就是上面这一行：只问 3 样——① 仓库地址 ② 授权（过程中点 Authorize / 始终允许）③ 豆包 API Key，
# 其余全自动，最后真跑一遍 T、Y 两条链路自检。
# 第 2 步：复制一条 B站 链接，按 ⌃⌘T（免费）或 ⌃⌘Y（精修）。
#
# 前提与限制条件见 README「限制条件」。可以反复跑：哪里坏了就整条重跑，做过的步骤自动跳过。
#
# 测试用的环境变量（平时不用管）：
#   ZX_ROOT=<目录> 装到别处   ZX_REPO=<地址> ZX_BRANCH=<分支> 指定来源   --test 演练：不动快捷键、不写 Netlify
#   --ci  无人值守（GitHub Actions 的临时 macOS 虚拟机用）：不提问；缺哪样凭据就跳过依赖它的步骤，自检里标「跳过」
#         凭据走环境变量：VOLC_SPEECH_API_KEY、NETLIFY_AUTH_TOKEN、ZX_BILI_COOKIE（cookie JSON 文件路径）
set -u
setopt pipefail
REPO_DEFAULT=${ZX_REPO:-https://github.com/bobsybrashin/bili-transcribe-crosscheck.git}
BRANCH=${ZX_BRANCH:-main}
SITE_NAME=zhuanxieku
SITE_URL=https://zhuanxieku.netlify.app
ROOT=${ZX_ROOT:-$HOME/Documents/转写库}
CFG=$HOME/.config/transcribe
ZENV=$HOME/.zshenv
TEST=0; CI_MODE=0
[[ ${1:-} == --test ]] && TEST=1
[[ ${1:-} == --ci ]] && { TEST=1; CI_MODE=1; export ZX_CI=1; }
# 和 src/hotkey.sh 同一条 PATH：这里能跑通，热键就能跑通
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

tmo()  { perl -e 'alarm shift; exec @ARGV' "$@" }      # 限时执行（macOS 没有 timeout）
step() { print "\n▶ $1" }
ok()   { print "  ✓ $1" }
die()  { print "  ✗ $1\n\n没装完。按上面这条处理后，再跑一次同一行命令（做过的会自动跳过）。"; exit 1 }
setenv() {   # 写进 ~/.zshenv：热键启动的 zsh 只读这个文件，不读 .zshrc
  touch $ZENV
  { grep -v "^export $1=" $ZENV || true; print -r -- "export $1='$2'" } > $ZENV.tmp && mv $ZENV.tmp $ZENV
}

# ── 第 1 步：3 个问题 ─────────────────────────────────────────
[[ $(uname) == Darwin ]] || die "只支持 macOS"
print "转写库 · 一步安装。先答 3 个问题，后面全自动（约 3–5 分钟）。"
print "前提：这台 Mac 的 Chrome 已登录 bilibili.com；Netlify 账号拥有 $SITE_NAME 站点。\n"
REPO=""; VKEY=""
if (( ! CI_MODE )); then
  read "REPO?① 仓库地址（回车用默认 $REPO_DEFAULT）："
  print "② 授权：接下来可能依次弹出——装 Homebrew 时输开机密码、浏览器里 Netlify 授权页点 Authorize、"
  print "   钥匙串窗口输开机密码并点「始终允许」。照点即可，不用回到这里操作。"
  read -s "VKEY?③ 豆包语音 API Key（火山引擎新版控制台 → API Key 管理；输入不显示；配过的直接回车）：" ; print
fi
REPO=${REPO:-$REPO_DEFAULT}
[[ -n $VKEY ]] || VKEY=${VOLC_SPEECH_API_KEY:-}
[[ -n $VKEY ]] || (( CI_MODE )) || die "没有 API Key"

# ── 之后全自动 ───────────────────────────────────────────────
step "1/8 工具"
if ! command -v brew >/dev/null; then
  print "  · 没有 Homebrew，现在装（会要开机密码）"
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || die "Homebrew 没装上"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi
for t in git python3 ffmpeg yt-dlp node; do
  pkg=$t; [[ $t == python3 ]] && pkg=python
  command -v $t >/dev/null || brew install $pkg >/dev/null 2>&1 || die "brew install $pkg 失败"
done
command -v netlify >/dev/null || npm install -g netlify-cli --no-fund --no-audit >/dev/null 2>&1 || die "装 netlify-cli 失败"
ok "git · python3 · ffmpeg · yt-dlp · node · netlify"

step "2/8 仓库 → $ROOT"
if [[ -d $ROOT/.git ]]; then
  git -C $ROOT fetch -q origin $BRANCH 2>/dev/null && git -C $ROOT merge -q --ff-only FETCH_HEAD 2>/dev/null \
    || print "  · 拉更新没成功，沿用本地版本"
else
  mkdir -p ${ROOT:h} && git clone -q -b $BRANCH $REPO $ROOT || die "克隆失败：$REPO"
fi
[[ -e $ROOT/bin ]] || ln -s src $ROOT/bin                       # 转写技能里的命令写的是 bin/
grep -qx bin $ROOT/.git/info/exclude 2>/dev/null || print bin >> $ROOT/.git/info/exclude
chmod +x $ROOT/src/*.py $ROOT/src/hotkey.sh $ROOT/setup/*.sh $ROOT/setup/*.py
(cd $ROOT && npm install --no-fund --no-audit --silent >/dev/null 2>&1) || die "npm install 失败"
ok "$(git -C $ROOT log -1 --format='%h %s')"
S=$ROOT/setup

step "3/8 Netlify 登录、关联 $SITE_NAME"
cd $ROOT
if (( CI_MODE )) && [[ -z ${NETLIFY_AUTH_TOKEN:-} ]]; then
  print "  · 无人值守且没有 NETLIFY_AUTH_TOKEN：跳过（只影响发布，不影响出稿）"
else
if [[ -z ${NETLIFY_AUTH_TOKEN:-} ]] && tmo 90 netlify status </dev/null 2>&1 | grep -q "Not logged in"; then
  print "  · 浏览器会打开 Netlify 授权页，点 Authorize"
  netlify login || die "Netlify 登录失败"
fi
[[ -f .netlify/state.json ]] || tmo 90 netlify link --name $SITE_NAME </dev/null >/dev/null 2>&1 \
  || die "关联不上 $SITE_NAME（登录的 Netlify 账号里没有这个站点？）"
ok "已关联"
fi

step "4/8 从站点还原已有文稿（不还原就部署，站上旧稿会被整站覆盖）"
python3 $S/restore-site.py $ROOT || die "还原失败"

step "5/8 B站 登录态"
mkdir -p $CFG && chmod 700 $CFG
if [[ -n ${ZX_BILI_COOKIE:-} && -f ${ZX_BILI_COOKIE:-/nonexistent} ]]; then   # 无人值守测试：直接给 cookie 文件
  install -m 600 $ZX_BILI_COOKIE $CFG/bilibili-cookie.json && ok "用了给定的 cookie 文件"
elif (( CI_MODE )); then
  print "  · 无人值守且没给 cookie：跳过（免费链路自检会标「跳过」）"
elif ! $S/refresh-cookie.sh; then
  read "?  · 钥匙串窗口点了「始终允许」后按回车重试（Chrome 没登录 B站 就先去登录）："
  $S/refresh-cookie.sh || die "没拿到 B站 登录态"
fi

step "6/8 密钥（写进 ~/.zshenv，热键才读得到）"
[[ -n $VKEY ]] && setenv VOLC_SPEECH_API_KEY "$VKEY" && export VOLC_SPEECH_API_KEY=$VKEY   # 环境里给的也落进 ~/.zshenv
WK=$(curl -fsS $SITE_URL/ | grep -o "KEY='[^']*'" | head -1 | cut -d"'" -f2)
[[ -n $WK ]] || die "线上页面里读不到写入密钥"
setenv SITE_WRITE_KEY "$WK"                                      # 沿用线上的值，各设备的收藏照常同步
if (( ! TEST )); then
  # netlify CLI 偶尔写完值却不退出（实测 env:set 会挂住），所以限时跑、再读回来核对
  nget() { tmo 90 netlify env:get ZHUANXIE_KEY --context production </dev/null 2>/dev/null | tail -1 }
  if [[ $(nget) != $WK ]]; then
    tmo 90 netlify env:set ZHUANXIE_KEY "$WK" --context production </dev/null >/dev/null 2>&1
    [[ $(nget) == $WK ]] || die "设置 Netlify 的 ZHUANXIE_KEY 失败"
  fi
  $S/cloud-secrets.sh || die "云端转写密钥没放上去"
fi
if (( TEST )); then
  ok "站点写入密钥已就位${VKEY:+、豆包 API Key 已就位}（演练：Netlify 和云端的密钥没动）"
else
  ok "豆包 API Key、站点写入密钥、云端转写密钥都已就位"
fi

step "7/8 快捷键：⌃⌘T 免费 · ⌃⌘Y 精修"
if (( TEST )); then
  print "  · 演练模式：跳过（不改真实快捷键）"
else
  for name mode key in 转写-免费 fast '@^t' 转写-精修 fine '@^y'; do
    d=$HOME/Library/Services/$name.workflow/Contents; mkdir -p $d
    python3 - $S/service.wflow $d $name "nohup \"$ROOT/src/hotkey.sh\" $mode >/dev/null 2>&1 &" <<'PY'
import sys, plistlib, pathlib, uuid
tpl, d, name, cmd = sys.argv[1:]
w = plistlib.loads(pathlib.Path(tpl).read_bytes())
a = w['actions'][0]['action']
a['ActionParameters']['COMMAND_STRING'] = cmd          # 立刻返回，转写在后台跑，进度靠通知
for k in ('InputUUID', 'OutputUUID', 'UUID'):
    a[k] = str(uuid.uuid4()).upper()
pathlib.Path(d, 'document.wflow').write_bytes(plistlib.dumps(w))
# Info.plist 只留这四个键：多写空字段，服务不注册且不报错
pathlib.Path(d, 'Info.plist').write_bytes(plistlib.dumps({'NSServices': [{
    'NSBackgroundColorName': 'background', 'NSIconName': 'NSActionTemplate',
    'NSMenuItem': {'default': name}, 'NSMessage': 'runWorkflowAsService'}]}))
PY
    # 键名外面那层双引号不能省：不加的话 (null) 会被当成数组
    defaults write pbs NSServicesStatus -dict-add "\"(null) - $name - runWorkflowAsService\"" "{key_equivalent = \"$key\";}"
  done
  /System/Library/CoreServices/pbs -update
  (( $(/System/Library/CoreServices/pbs -dump 2>/dev/null | grep -c 'U8f6c\\U5199-') >= 4 )) || die "系统没认到两个服务"
  ok "两个服务已注册并绑好键"
fi

step "8/8 自检（真跑 T、Y 两条链路的关键环节，约 30 秒，花费约 0.001 元）"
python3 $S/selfcheck.py $ROOT || die "自检没过"
(( TEST )) || osascript -e 'display notification "复制 B站 链接后按 ⌃⌘T 免费 / ⌃⌘Y 精修" with title "转写" subtitle "安装完成"'

print "\n✅ 装好了。第 2 步：复制一条 B站 链接 → 按 ⌃⌘T（免费）或 ⌃⌘Y（精修），出稿后弹通知。"
[[ -s $CFG/cloud-pass ]] && print "   备用：$SITE_URL 首页「云端转写」，口令 $(cat $CFG/cloud-pass)（每台设备输一次）"
exit 0                                                         # 上一行的判断为假时别把 1 当成退出码
