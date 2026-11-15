# bili-transcribe-crosscheck

## 一步安装

在 Mac 的「终端」里粘贴这一行，回车：

```bash
zsh -c "$(curl -fsSL https://raw.githubusercontent.com/bobsybrashin/bili-transcribe-crosscheck/main/install.sh)"
```

它只问 3 样：**① 仓库地址**（回车用默认）**② 授权**（过程中弹窗点 Authorize / 始终允许）**③ 豆包 API Key**。
其余全自动——装工具、拉仓库、还原站上已有文稿、取 B站 登录态、对好站点和云端密钥、绑快捷键——最后真跑一遍两条链路自检。

**第 2 步就是验收**：复制一条 B站 链接，按 <kbd>⌃⌘T</kbd>（免费）或 <kbd>⌃⌘Y</kbd>（精修）。
每按一次都是一个「任务」：分步记录，结束时弹通知并打开任务页——成功写字数、花费、待核项，稿子同时放上站点「新稿」区（不发布、不花额度）；失败写**卡在哪一步、原因、怎么办**。站点首页「最近任务」能看到最近几次，手机上也能看。
不在 Mac 前、热键不灵或授权出问题时，用站点首页的「云端转写」框（同样 T / Y 两个按钮）。

**整理稿同步**（不在 B站 的视频、英文材料、自己整理的文字）：把文稿存成 `.md` 或 `.txt`，在访达里选中按 <kbd>⌃⌘U</kbd>
（或右键 → 快速操作 → 同步到转写库），一步收进 `文稿/` 并放上站点「新稿」区。英文一段、中文一段交替写，网站自动排成中英对照。
格式见 [`src/upload.py`](src/upload.py) 开头；头部（标题、讲者、日期、原文链接）都可以省。也可以让 Claude 先替你整理好（比如逐段翻译成中英对照），放进 `投稿/` 再同步。

设计原则：**人只做机器做不了的事**——给出仓库地址、点授权、填 API Key。别的都不该问。
脚本可以反复跑：哪里坏了就整条重跑，做过的步骤自动跳过。

### 限制条件

当下或短期不解决的，直接写成前提：

| # | 限制 | 说明 |
|---|---|---|
| 1 | 只支持 macOS | 热键靠 macOS 的「服务」；需要能输开机密码的账户（装 Homebrew 时用） |
| 2 | Chrome 里要已登录 bilibili.com | B站 登录态从 Chrome 取；约一个月过期，跑 `setup/refresh-cookie.sh` 续上（云端同步更新） |
| 3 | Netlify 账号要拥有 `zhuanxieku` 站点 | 这套只服务这一个站；别的账号/新站点不在本次范围 |
| 4 | 豆包语音要已开通「录音文件识别 2.0」 | API Key 取自火山引擎**新版**控制台；旧版的 App ID 用不了 |
| 5 | 过程中有系统弹窗要人点 | Netlify 授权、钥匙串（输开机密码 + 始终允许）、首次通知权限 |
| 6 | 热键在少数应用里不生效 | Electron 类应用（如 Claude 桌面版）里按没反应；在 Chrome、访达里按 |
| 7 | 免费路线（T）要视频自带中文字幕 | 没有字幕就只能精修（Y） |
| 8 | 云端 Y 有上限 | 单条 ≤ 2 小时；没有热词表、不做双源核对，标「云端精修·未核」 |
| 9 | Netlify 免费额度 300/月，硬上限 | 每次正式部署 15；超了站点暂停到下月。出稿不花额度，只有发布花 |
| 10 | 整理稿只收 `.md` / `.txt` | Word、PDF 先另存为纯文本；⌃⌘U 只在访达里有效 |
| 11 | 全新机器的验证方式 | GitHub Actions 的临时 macOS 虚拟机做无人值守安装测试；人点的弹窗环节只能在真机验 |

---

1. **B站链接转成文字稿**
2. **发布成静态网页**，手机上读
3. **双源交叉核对**

| 做什么 | 怎么样 |
|---|---|
| 一键触发 | macOS 绑快捷键，复制链接按一下就出稿（见 [2.4](#24-绑快捷键macos)） |
| 转文字 · 快车道 | 平台字幕，约 1 秒，免费 |
| 转文字 · 精修 | 豆包 Seed-ASR，约 0.8 元/小时，带标点和说话人 |
| 双源核对 | 两条独立链路比对，只报它们打架的地方 |
| 发布 | 生成静态站，手机上读 |

先跑 `python3 example.py`，零配置、零联网、不花钱：

```
一、结构质检（四道闸）看源A —— 单源能看出什么
  chars  300
  cps    1.667
  loop   0.0
  tail   0.98
  判定    PASS   四道闸全过

二、双源交叉核验 —— 拿第二个来源去查第一个
  divergence()   2 处
     [替换] …九八零年铺设的材质以灰口
          源A: 柱体
          源B: 铸铁
     [A缺] …损不等于爆管爆管是显性的
          源A: （没有）
          源B: 抢修队两小时就到现场

  negation_check()   1 处      ← 一字之差可翻转语义，长度阈值必然漏掉，所以单独查
     …多年我们推广得并不快原因 ｜ 源A: （没有）  源B: 不

  number_check()   2 处        ← 数字没有语义冗余，读上去不会别扭，只能靠数
     1970：源A 出现 0 次，源B 出现 1 次
     1980：源A 出现 1 次，源B 出现 0 次
```

四道闸说 PASS，双源核验找出 5 处——为什么必须有第二个来源，见 [3 · 方法](#3--方法为什么必须有第二个来源)。

---

## 1 · 快速开始

**不需要 API key，不联网，不装任何依赖。**

```bash
git clone https://github.com/bobsybrashin/bili-transcribe-crosscheck.git && cd bili-transcribe-crosscheck
python3 example.py
```

上面那段输出就是它打印的。两段示例文本是编的，里面埋了四类问题——替换、
单侧整段缺失、否定词翻转、数字不符——四道闸全部放行，四个检测各抓各的。

想只拿方法走：`src/qc.py` 和 `src/merge.py` **都是零第三方依赖的单文件**，
直接复制进你自己的项目即可。

---

## 2 · 搭完整链路

三段能力，按需装，互不依赖：

| 想要什么 | 要装 | 要配 |
|---|---|---|
| 只验证方法 | 无 | 无 |
| 快车道：平台字幕出稿 | `python3` | B站 cookie |
| 精修：付费 ASR + 双源核验 | `+ ffmpeg` `yt-dlp` | `+ VOLC_SPEECH_API_KEY` |
| 多设备阅读的静态站 | `+ node` `netlify-cli` | `+ SITE_WRITE_KEY` |

```bash
brew install ffmpeg yt-dlp node
npm install -g netlify-cli
npm install                 # 只为 netlify function 的 @netlify/blobs
```

### 2.1 B站 cookie

未登录时字幕接口返回空轨，所以这一步不是可选的。

默认读 `~/.config/transcribe/bilibili-cookie.json`，用环境变量 `BILI_COOKIE_JSON` 换路径。
浏览器登录 bilibili.com 后从 Cookie 里取三项，填成：

```json
{
  "sessdata": "<SESSDATA 的值>",
  "bili_jct": "<bili_jct 的值>",
  "dede_user_id": "<DedeUserID 的值>"
}
```

```bash
mkdir -p ~/.config/transcribe && chmod 700 ~/.config/transcribe
```

cookie 有效期约一个月，过期表现为接口返回空字幕轨而不是报错——重新取一次即可。

### 2.2 付费 ASR（火山引擎 / 豆包）

控制台开通「语音技术 → 录音文件识别」，拿到 API Key 后：

```bash
export VOLC_SPEECH_API_KEY='...'      # 写进 ~/.zshrc
```

**资源 ID 用 `volc.seedasr.auc`。** 官方 flash 接口文档写的是 `volc.bigasr.auc_turbo`，
那个在账号里不存在，照文档填必然返回 `45000030`。见坑表第 1 条。

计费按音频时长走，实测约 0.8 元/小时。跑之前 CLI 会把这条视频的花费算给你看。

> **这一条会读你本机的浏览器 cookie。** 精修要先下音频，`src/fetch.py` 调用
> `yt-dlp --cookies-from-browser chrome` 借用登录态拿高码率音轨——它会去读 Chrome
> 的 cookie 数据库，macOS 上还会弹一次钥匙串授权。不想给就关掉：
>
> ```bash
> export YTDLP_COOKIES_FROM_BROWSER=''      # 换别的浏览器就填 firefox / edge / safari
> ```
>
> 关掉之后只能下到游客可见的码率，对语音识别够用，但音质会差一些。

### 2.3 静态站（Netlify）

```bash
python3 src/publish.py            # 默认只构建到 site/
python3 src/publish.py --serve    # 本地预览，不占部署额度
python3 src/publish.py --deploy   # 确定要推的时候才用
```

收藏权重要跨设备同步的话，**同一个密钥值要设两处**：

| 在哪 | 变量名 | 作用 |
|---|---|---|
| 本机构建时 | `SITE_WRITE_KEY` | 烤进页面，前端带着它写 |
| Netlify 站点环境变量 | `ZHUANXIE_KEY` | function 校验来访者 |

（两个名字不一样是历史遗留，功能上必须同值。介意的话改 `netlify/functions/w.mjs` 里那一行。）

**不设 `SITE_WRITE_KEY` 就生成只读站**，不会报错：权重照读照显示，你点的星只留在
本机 localStorage。密钥烤进页面意味着翻源码的人能拿到它——挡得住偶然撞见网址的人，
仅此而已，别往这个站放更敏感的东西。

### 2.4 绑快捷键（macOS）

`src/hotkey.sh` 读剪贴板里的链接直接出稿。挂成 Service 就能全局按键触发：

```
~/Library/Services/Transcribe Fast.workflow/Contents/
├── Info.plist
└── document.wflow
```

`Info.plist` —— **只留这四个键**。多写 `NSSendTypes`、`NSRequiredContext` 之类的空字段，
Service 不会注册，而且系统不报任何错，你只会发现快捷键设置里搜不到它：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>NSServices</key><array><dict>
    <key>NSBackgroundColorName</key><string>background</string>
    <key>NSIconName</key><string>NSActionTemplate</string>
    <key>NSMenuItem</key><dict><key>default</key><string>Transcribe Fast</string></dict>
    <key>NSMessage</key><string>runWorkflowAsService</string>
  </dict></array>
</dict></plist>
```

`document.wflow` 用 Automator 建一个「Run Shell Script」动作，shell 选 `/bin/zsh`，
`workflowTypeIdentifier` 是 `com.apple.Automator.servicesMenu`，命令写：

```
/绝对路径/bili-transcribe-crosscheck/src/hotkey.sh fast
```

然后在 系统设置 → 键盘 → 键盘快捷键 → 服务 里给它绑键。

> **Service 启动时 PATH 是精简的**，`netlify`、`yt-dlp`、`ffmpeg` 都不在里面。
> `hotkey.sh` 顶部那行 `export PATH` 不能删——少了它的表现是**出稿成功、发布静默失败**，
> 没有任何报错，你会以为整条链路跑通了。

### 2.5 日常命令

```bash
python3 src/ts.py <url>              # 开跑前当面问走哪条路，把耗时和花费摆出来
python3 src/ts.py <url> --fast       # 快车道：平台字幕，约 1 秒，免费
python3 src/ts.py <url> --fine       # 精修：付费 ASR + 双源核对
python3 src/ts.py <url> --fine --solo            # 单人口播，见坑表第 7 条
python3 src/ts.py <url> --fine --speakers 主持人,嘉宾
python3 src/ts.py --review <BV>      # 改完 tables/ 后走缓存重出，零额度
python3 src/ts.py --finalize <BV>    # 定稿：重出最终稿并删光过程文件

python3 src/ts.py <合集或UP主空间url>            # 批量，默认增量只补新的
python3 src/ts.py <同上> --fine --yes            # 批量精修要 --yes 确认花费

python3 src/doctor.py                # 对账：找失败残骸和站点不一致
python3 src/doctor.py --fix          # 补发布、删残骸、清音频
```

单视频链接吃 BV 号 / b23.tv 短链 / 番剧 ep·ss。批量里单条失败不中断。

> **批量之前先估一下会发出多少次请求。** 一个 UP 主空间的全量投稿会按 50 条一页翻到底，
> 几百条视频就是几百次接口调用。代码里翻页之间留了 0.4 秒间隔，但这不是免死金牌——
> 一次性把别人的整个空间抓干净，账号被风控是自找的。
> 先用单条链接确认链路通了，再考虑批量，并且分批跑。

`tables/` 是这套东西唯一的长期资产，比流水线代码更值得维护：

```
tables/hot/<UP主>.json   热词表，识别时生效 —— 事后补要重花额度
tables/fix/<UP主>.json   替换表，出稿时生效 —— 随时能补，改完 --review 重出
tables/*/_default.json   对所有来源生效，与来源表叠加
```

写替换表只写**有依据的**替换，拿不准的只标不改。猜测写进正文比留着错更糟——
错能被发现，伪装成正确的猜测不能。替换串要带长上下文，避免误伤合法用法。

---

## 3 · 方法：为什么必须有第二个来源

### 3.1 单源看不出自己的错

一套 ASR 的输出只有一个自洽的版本。它把「不是」听成「是」、把一整句吞掉，
你拿到的仍然是一段通顺的中文。常见的自检手段全都失效：

- **置信度**：实测该 ASR 返回的 `word.confidence` 恒为 0（六万多个词全是 0），
  这个字段直接不可用。
- **结构质检**：字数、字符密度、循环重复率、尾部覆盖率——删掉一句话，这四个值都正常。
- **孤词法**（只出现一次的英文词是错误高发区）：在纯中文内容里直接归零，
  实测一篇政经口播全文只有十几个英文词。

所以只能横向比：**两条独立链路同一处给出不同的字，至少有一边错了。**

### 3.2 锚点对齐

两个来源的分句、标点、语气词都不同，按时间轴硬对会错位。做法是用内容本身当锚点：

1. **归一**：去标点、去语气词（`呃嗯啊哦诶哎嘛呀吧`）、转小写，只留下字。
2. **找唯一锚点**：取所有长度 10 的子串，保留**在 A 里只出现一次、在 B 里也只出现一次**的。
   唯一性是关键——重复出现的片段会把对齐拉到错误的位置。
3. **最长递增子序列**：锚点对 `(位置A, 位置B)` 必须单调递增。不递增的是假锚点，剔掉。
   这一步是全部可靠性的来源。
4. **段内 diff**：相邻锚点之间的文本各自做 `difflib`，只看差异块。

### 3.3 四类检测，各防各的

| 检测 | 抓什么 | 为什么要单列 |
|---|---|---|
| `divergence` 替换 | 两边给出不同实词 | 主力。带长度比例过滤（一边远长于另一边 = 对齐错位，不是真分歧），否则清单会被噪声淹没 |
| `divergence` 单侧缺失 | 一边整段没有（≥6 字） | **最危险的一类**。只报「替换」会把它全漏掉——它不是听错，是不见 |
| `negation_check` | 否定词数量不一致 | 「不」字之差可以翻转整句语义，但长度只有 1，替换类的阈值（≥2 字）必然漏 |
| `number_check` | 两边数字集合不同 | 数字没有语义冗余，读上去不会别扭，人也校不出来，只能对着数 |

四类都在 `src/qc.py`，一个文件，零第三方依赖。

---

## 4 · 已知坑

每条都是实测撞出来的。前三条几乎人人会撞。

| # | 坑 | 为什么你也会撞上 |
|---|---|---|
| 1 | **资源 ID 是 `volc.seedasr.auc`** | 官方 flash 接口文档写的是 `volc.bigasr.auc_turbo`，但账号里不存在这个资源。你会照文档填，然后拿到 `45000030`，而错误信息不会告诉你该换成什么 |
| 2 | **`confidence` 恒为 0** | 字段存在、类型正确、不报错，你会很自然地拿它做告警阈值——然后发现一条都不告警。实测样本六万多个词全是 0。只能用双源分歧代替 |
| 3 | **平台 AI 字幕会整段删内容** | 不是听错，是**不见**。实测样本：28 分钟音频缺 21 处约 350 字（3.7%），明显偏向人名。删完之后文字依然通顺，四道闸一道都不响。你会以为拿到了完整文稿，并且拿它去计数、去引用 |
| 4 | **分段的 speaker 编号不跨段通用** | 每段独立编号，段与段之间没有任何对应关系。实测 4 段里有 3 段是反的。不做重叠区对齐，双人对话会整段串台，而输出看上去完全正常 |
| 5 | **切段裁切点两侧口径必须一致** | 段 i 覆盖 `[i·3600−60, (i+1)·3600]`，裁切点统一取 `(i+1)·3600−30`。两侧各算各的，接缝处会重复约 90 秒——刚好长到你以为是 ASR 抽风 |
| 6 | **孤词法在纯中文内容里失效** | 它靠「只出现一次的英文词」定位错误。中文口播全文可能只有十几个英文词，孤词清单恒为空。你会以为这段特别干净 |
| 7 | **单人口播会被判成两人** | 实测单人视频被识别出 2 个说话人，次要那个占 12% 的字数——「零散说话人自动合并」那种 2% 的阈值根本兜不住。只能从源头关掉 `enable_speaker_info`（`--solo`） |
| 8 | **Netlify CDN 会缓存 `/api/w` 的 GET** | 响应头写了 `cache-control: no-store` 也照缓存不误，你会看到 `age: 2` 这种东西，然后怀疑自己的写入逻辑。客户端读必须带时间戳绕开。另外 Blobs 是最终一致，写完约 4 秒才能读到 |
| 9 | **部署有额度，默认只构建** | 改一次推一次会很快烧穿免费额度，实测一天 19 次就推穿了，当天站点无法更新。所以 `publish.py` 的默认行为是只生成 `site/`，`--serve` 本地看，`--deploy` 才推 |

两条通用规格，省得你试：音频压到 `ffmpeg -ar 16000 -ac 1 -b:a 24k`（约 0.17 MB/分钟）；
flash 接口上限 2 小时 / 100MB，本仓库按 1 小时一段、base64 后约 14MB。

B站 的 `x/web-interface/view` 接口从部分海外 IP 调用会返回 412。`src/fetch.py` 里的
`aid` 是用 `bv2av` 纯本地算出来的，不依赖这个接口，所以即使 412 也照样能取到字幕——
只是 UP 主名和发布日期会缺。

---

## 5 · 这套方法的边界

写在前面，别把它当成质量保证：

- **两套 ASR 同时错，永远查不出来。** 两边把同一个人名听成同一个错字时，
  比对结果是「一致」。实测撞到过不止一次。人名、专有名词尤其容易同时错——
  它们恰好是最值得引用的部分。
- **它只能定位分歧，不能判定谁对。** 输出是一份待核清单，最后仍然要人去读、去定夺。
  自动选一边等于把两个来源的错并集起来。
- **结构质检和双源核验是两回事。** 四道闸查的是「有没有崩」，双源查的是「有没有错」。
  前者过了完全不代表后者没事——`example.py` 演示的就是这个。
- **热词表必须在识别之前配好**，它在识别那一刻生效。事后发现漏配只能重跑，重花钱。
- 覆盖面只到 B站。`src/fetch.py` 是取源抽象层，换来源只改这一个文件；
  YouTube 留了分支位（yt-dlp 能同时拿字幕和音频），微信视频号没有公开接口。

---

## 6 · 目录

```
example.py              零配置演示，先跑这个
src/qc.py               ★ 四道闸 + 孤词 + 双源分歧 + 否定词 + 数字。零依赖，可单独拿走
src/merge.py            ★ 说话人跨段对齐、成段。零依赖，可单独拿走
src/asr.py              付费 ASR 封装（分段、热词、重试）
src/bili.py             B站 接口：WBI 签名、字幕轨、投稿清单
src/fetch.py            取源抽象层 —— 换视频来源只改这一个文件
src/ts.py               CLI 入口
src/publish.py          生成静态站（默认只构建）
src/doctor.py           对账：找失败残骸和不一致
src/hotkey.sh           macOS 热键入口
netlify/functions/w.mjs 收藏权重同步（GET 公开读，POST 校验密钥）
tables/                 热词表与替换表，唯一的长期资产
```

运行时产生但不进仓库：`文稿/`（成品）、`site/`（生成的站）、`.work/`（分段缓存与待核清单）。
