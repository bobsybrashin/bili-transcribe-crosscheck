// 热键守护进程：常驻后台，直接向系统注册全局热键，按下就跑脚本。
//   ⌃⌘T → hotkey.sh fast（免费）   ⌃⌘Y → hotkey.sh fine（精修）   ⌃⌘U → 访达里选中的文稿 → upload.py
// 为什么不用「服务」(Automator 快速操作)：系统的 WorkflowServiceRunner 会卡住——按键后运行器起来了、脚本却不跑，
// 而且不报任何错（2026-11-20 实测）。RegisterEventHotKey 不需要辅助功能权限，由 launchd 拉起、挂了自动重启。
// 用法：zxhotkey <库根目录>     日志：~/Library/Logs/转写热键.log（不在 文稿 所在的受保护目录里，出事也写得进）
import AppKit
import Carbon

let root = CommandLine.arguments.count > 1 ? CommandLine.arguments[1]
         : FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents/转写库").path
let logURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/转写热键.log")

func log(_ s: String) {
    let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM-dd HH:mm:ss"
    let line = "\(f.string(from: Date()))  \(s)\n"
    if let h = try? FileHandle(forWritingTo: logURL) { h.seekToEndOfFile(); h.write(line.data(using: .utf8)!); h.closeFile() }
    else { try? line.write(to: logURL, atomically: true, encoding: .utf8) }
}

func notify(_ title: String, _ body: String) {
    let esc = { (s: String) in s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") }
    NSAppleScript(source: "display notification \"\(esc(body))\" with title \"转写\" subtitle \"\(esc(title))\"")?.executeAndReturnError(nil)
}

// 用登录 shell 的 zsh 跑：它会读 ~/.zshenv（豆包 Key 等都在那里），和原来的服务一致
func run(_ args: [String], _ what: String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/zsh")
    p.arguments = args
    var env = ProcessInfo.processInfo.environment
    env["PATH"] = "/opt/homebrew/bin:\(NSHomeDirectory())/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    env["LANG"] = "en_US.UTF-8"; env["LC_ALL"] = "en_US.UTF-8"
    p.environment = env
    if let h = try? FileHandle(forWritingTo: logURL) { h.seekToEndOfFile(); p.standardOutput = h; p.standardError = h }
    p.terminationHandler = { log("\(what) 结束，退出码 \($0.terminationStatus)") }
    do { try p.run(); log("\(what) 已启动 pid=\(p.processIdentifier)") }
    catch { log("\(what) 启动失败：\(error)"); notify("❌ 没启动", "\(error)") }
}

func finderSelection() -> [String] {
    let src = """
    tell application "Finder"
      set out to ""
      repeat with f in (get selection)
        set out to out & POSIX path of (f as alias) & linefeed
      end repeat
      return out
    end tell
    """
    var err: NSDictionary?
    let r = NSAppleScript(source: src)?.executeAndReturnError(&err)
    if let err = err { log("读访达选中失败：\(err)") }
    return (r?.stringValue ?? "").split(separator: "\n").map(String.init).filter { !$0.isEmpty }
}

var last: [UInt32: Date] = [:]
func fire(_ id: UInt32) {
    // 防连按：同一个键 5 秒内只算一次（之前连按两次 Y 会花两份钱）
    if let t = last[id], Date().timeIntervalSince(t) < 5 { log("键 \(id) 5 秒内重复，忽略"); return }
    last[id] = Date()
    switch id {
    case 1: run(["\(root)/src/hotkey.sh", "fast"], "⌃⌘T 免费")
    case 2: run(["\(root)/src/hotkey.sh", "fine"], "⌃⌘Y 精修")
    case 3:
        let files = finderSelection()
        if files.isEmpty { notify("⌃⌘U 没选中文件", "先在访达里选中整理好的文稿，再按 ⌃⌘U"); log("⌃⌘U 访达里没选中"); return }
        run(["-c", "\"$0\" \"$@\"", "\(root)/src/upload.py"] + files, "⌃⌘U 同步 \(files.count) 个")
    default: break
    }
}

var handler: EventHandlerRef?
var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
InstallEventHandler(GetApplicationEventTarget(), { _, ev, _ in
    var hk = EventHotKeyID()
    GetEventParameter(ev, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
                      MemoryLayout<EventHotKeyID>.size, nil, &hk)
    fire(hk.id)
    return noErr
}, 1, &spec, nil, &handler)

let mods = UInt32(controlKey | cmdKey)
var refs: [EventHotKeyRef?] = []
for (id, code, name) in [(UInt32(1), kVK_ANSI_T, "⌃⌘T"), (2, kVK_ANSI_Y, "⌃⌘Y"), (3, kVK_ANSI_U, "⌃⌘U")] {
    var ref: EventHotKeyRef?
    let st = RegisterEventHotKey(UInt32(code), mods, EventHotKeyID(signature: OSType(0x5A58484B), id: id),
                                 GetApplicationEventTarget(), 0, &ref)
    log(st == noErr ? "\(name) 已注册" : "\(name) 注册失败（\(st)，可能被别的程序占了）")
    refs.append(ref)
}
// 启动时碰一下库目录：库在「文稿」里时，系统第一次会弹「是否允许访问文稿文件夹」，趁安装时人在场点掉
let ok = (try? FileManager.default.contentsOfDirectory(atPath: "\(root)/src")) != nil
log("热键守护进程已启动，库目录 \(root)，\(ok ? "可读" : "读不到（去 系统设置 → 隐私与安全性 → 文件和文件夹 允许 zxhotkey）")")

NSApplication.shared.setActivationPolicy(.prohibited)
NSApplication.shared.run()
