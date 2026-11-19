#!/bin/zsh
# 装热键守护进程：编译 src/hotkeyd.swift → ~/Library/Application Support/转写库/zxhotkey，
# 用 LaunchAgent 开机自启、挂了自动重启；同时摘掉三个「服务」上的快捷键，免得一按跑两次（服务本身留着当右键菜单）。
#   setup/hotkeyd.sh <库根目录>      重跑无害
set -e
ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
BIN_DIR="$HOME/Library/Application Support/转写库"; BIN="$BIN_DIR/zxhotkey"
LABEL=com.zhuanxieku.hotkey; PL="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$BIN_DIR" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
swiftc -O -o "$BIN.new" "$ROOT/src/hotkeyd.swift" 2>&1 | grep -v '^$' || true
[[ -x "$BIN.new" ]] || { print "编译失败（需要 Xcode 命令行工具：xcode-select --install）"; exit 1; }
mv -f "$BIN.new" "$BIN"
cat > "$PL" <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$BIN</string><string>$ROOT</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
</dict></plist>
P
for name in 转写-免费 转写-精修 同步到转写库; do
  defaults write pbs NSServicesStatus -dict-add "\"(null) - $name - runWorkflowAsService\"" "{key_equivalent = \"\";}"
done
/System/Library/CoreServices/pbs -update
launchctl bootout gui/$UID/$LABEL 2>/dev/null || true
launchctl bootstrap gui/$UID "$PL"
sleep 1
tail -4 "$HOME/Library/Logs/转写热键.log"
grep -q '⌃⌘Y 已注册' <(tail -6 "$HOME/Library/Logs/转写热键.log") || { print "热键没注册上，看 ~/Library/Logs/转写热键.log"; exit 1; }
