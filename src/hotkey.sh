#!/bin/zsh
# 热键入口：读剪贴板里的链接 → 出稿 → 发布 → 通知
#   hotkey.sh fast   免费快车道（默认）
#   hotkey.sh fine   付费精修
# 绑定方式见 README「热键」一节。

set -u
# Service/Dock 启动时 PATH 是精简的，netlify(~/.local/bin)、yt-dlp+ffmpeg(/opt/homebrew/bin)
# 都不在里面。必须显式补齐，否则出稿成功但发布静默失败。
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
MODE="${1:-fast}"
# 仓库根目录：优先环境变量，否则按脚本自身位置推（本文件在 <root>/src/ 下）
ROOT="${TRANSCRIBE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LOG="$ROOT/.work/hotkey.log"
mkdir -p "$ROOT/.work"

notify() {  # $1=标题 $2=正文
  osascript -e "display notification \"$2\" with title \"转写\" subtitle \"$1\"" 2>/dev/null
}

URL="$(pbpaste | tr -d '\n' | head -c 500)"
case "$URL" in
  *bilibili.com*|*b23.tv*) ;;
  *) notify "剪贴板里不是 B站 链接" "先复制视频链接再按热键"; exit 1 ;;
esac

[ "$MODE" = "fine" ] && FLAG="--fine" || FLAG="--fast"
notify "开始（${MODE}）" "$(echo "$URL" | head -c 60)"

{
  echo "── $(date '+%F %T')  mode=$MODE  $URL"
  OUT="$("$ROOT/src/ts.py" "$URL" $FLAG 2>&1)"
  CODE=$?
  echo "$OUT"
} >> "$LOG" 2>&1

TITLE="$(printf '%s\n' "$OUT" | grep -m1 '^《' | tr -d '《》')"
if [ "$CODE" -ne 0 ]; then
  case "$CODE" in
    2) notify "没有中文字幕轨" "这条只能走精修" ;;
    3) notify "已有精修版" "快车道不覆盖它" ;;
    *) notify "失败（码 $CODE）" "看 .work/hotkey.log" ;;
  esac
  exit "$CODE"
fi

# 不在这里部署——发布有额度，每转一条推一次会烧穿。攒着，改完/转完再一次推。
PEND=$("$ROOT/src/publish.py" >/dev/null 2>&1; "$ROOT/src/doctor.py" 2>/dev/null \
       | grep -o "[0-9]* 篇文稿站上没有" | grep -o "^[0-9]*")
if [ -n "$PEND" ] && [ "$PEND" -gt 0 ] 2>/dev/null; then
  notify "已出稿 · 待发布 $PEND 篇" "${TITLE:-完成} · 跑 src/publish.py --deploy 推上去"
else
  notify "已出稿" "${TITLE:-完成}"
fi

# 收尾对账：有残留就提醒，不让失败悄悄堆积
LEFT="$("$ROOT/src/doctor.py" --quiet 2>/dev/null)"
if [ -n "$LEFT" ]; then
  notify "⚠️ 有残留待清理" "$LEFT · 跑 src/doctor.py --fix"
  echo "  残留: $LEFT" >> "$LOG"
fi
