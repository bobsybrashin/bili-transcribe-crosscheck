#!/bin/zsh
# 热键入口：读剪贴板里的链接 → 出稿 → 发布 → 通知
#   hotkey.sh fast   免费快车道（默认）
#   hotkey.sh fine   付费精修
# 绑定方式见 README「热键」一节。

set -u
# Service/Dock 启动时 PATH 是精简的，netlify(~/.local/bin)、yt-dlp+ffmpeg(/opt/homebrew/bin)
# 都不在里面。必须显式补齐，否则出稿成功但发布静默失败。
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# 服务启动时也没有语言环境：不设的话 pbpaste 会把剪贴板里的中文吐成 ???
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
MODE="${1:-fast}"
# 仓库根目录：优先环境变量，否则按脚本自身位置推（本文件在 <root>/src/ 下）
ROOT="${TRANSCRIBE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LOG="$ROOT/.work/hotkey.log"
mkdir -p "$ROOT/.work"

notify() {  # $1=标题 $2=正文
  osascript -e "display notification \"$2\" with title \"转写\" subtitle \"$1\"" 2>/dev/null
}

URL="$(pbpaste | tr -d '\n' | head -c 500)"
[ "$MODE" = "fine" ] && M=Y || M=T
notify "开始（$M）" "$(echo "$URL" | head -c 60)"

# 一次转写 = 一个任务：task.py 分步记录、出稿后放上网站「新稿」区（不发布、不花额度），
# 结束时弹通知并打开任务页——成功写标题/花费/待核项，失败写卡在哪一步、原因、怎么办。
# 剪贴板不是 B站 链接也交给它，同样给出任务页。
{
  echo "── $(date '+%F %T')  mode=$MODE  $URL"
  "$ROOT/src/task.py" "$M" "$URL" 2>&1
  CODE=$?
} >> "$LOG" 2>&1
[ "$CODE" -ne 0 ] && exit "$CODE"

# 本机站点照旧重建（doctor 对账用）。不在这里部署——发布有额度，攒着一次推。
"$ROOT/src/publish.py" >/dev/null 2>&1

# 收尾对账：有残留就提醒，不让失败悄悄堆积
LEFT="$("$ROOT/src/doctor.py" --quiet 2>/dev/null)"
if [ -n "$LEFT" ]; then
  notify "⚠️ 有残留待清理" "$LEFT · 跑 src/doctor.py --fix"
  echo "  残留: $LEFT" >> "$LOG"
fi
