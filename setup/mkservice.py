#!/usr/bin/env python3
"""生成热键用的「服务」（Automator 快速操作）。install.sh 调用；单独跑也行。
  mkservice.py <库根目录> text <名字> <命令>     不需要输入（热键转写：读剪贴板）
  mkservice.py <库根目录> files <名字> <命令>    Finder 里选中的文件作为参数（同步整理稿）
"""
import sys, plistlib, pathlib, uuid
root, kind, name, cmd = sys.argv[1:5]
tpl = pathlib.Path(__file__).with_name('service.wflow')
w = plistlib.loads(tpl.read_bytes())
a = w['actions'][0]['action']
a['ActionParameters']['COMMAND_STRING'] = cmd
for k in ('InputUUID', 'OutputUUID', 'UUID'):
    a[k] = str(uuid.uuid4()).upper()
m = w['workflowMetaData']
svc = {'NSBackgroundColorName': 'background', 'NSIconName': 'NSActionTemplate',
       'NSMenuItem': {'default': name}, 'NSMessage': 'runWorkflowAsService'}
if kind == 'files':
    a['ActionParameters']['inputMethod'] = 1                    # 选中的文件路径作为 "$@" 传进去
    m['inputTypeIdentifier'] = m['serviceInputTypeIdentifier'] = 'com.apple.Automator.fileSystemObject'
    m['serviceApplicationBundleID'] = 'com.apple.finder'
    m['serviceApplicationPath'] = '/System/Library/CoreServices/Finder.app'
    svc['NSRequiredContext'] = {'NSApplicationIdentifier': 'com.apple.finder'}
    svc['NSSendFileTypes'] = ['public.text']
else:
    m['inputTypeIdentifier'] = m['serviceInputTypeIdentifier'] = 'com.apple.Automator.nothing'
d = pathlib.Path.home() / 'Library/Services' / f'{name}.workflow/Contents'
d.mkdir(parents=True, exist_ok=True)
(d / 'document.wflow').write_bytes(plistlib.dumps(w))
# Info.plist 只放有值的键：写空字段（空的 NSSendTypes 之类）服务不注册且不报错
(d / 'Info.plist').write_bytes(plistlib.dumps({'NSServices': [svc]}))
print(f'  · 服务「{name}」已生成')
