# 影子（Shadow）

影子是一款面向 Windows 的轻量级摄像头隐私监控工具。

Shadow is a lightweight Windows tool for monitoring camera access.

当应用或浏览器使用摄像头时，影子会提醒用户，帮助发现未知或意外访问。

It notifies you when an app or browser accesses the camera.

## 功能

- 检测摄像头开启和关闭
- 识别正在使用摄像头的应用
- Windows 桌面通知
- 本地运行，不查看或保存画面

## Features

- Detect camera start and stop events
- Identify the app using the camera
- Windows desktop notifications
- Runs locally without viewing or saving camera footage

## 工作范围

影子只监控 Windows 记录的摄像头访问活动，不会录制或上传摄像头画面。

Shadow monitors camera access reported by Windows. It does not record or upload video.

网站通过浏览器使用摄像头时，通常只能识别浏览器进程，无法直接识别具体网页。

When a website uses the camera through a browser, Shadow may only identify the browser process, not the specific website.

影子用于检测和提醒，不能阻止所有访问，也不能替代杀毒软件或物理遮挡。

Shadow focuses on detection and alerts. It does not block all access and is not a replacement for antivirus software or a physical camera cover.

## 隐私原则

- 完全本地运行
- 不查看、录制或保存画面
- 不上传访问记录
- 不要求账号
- 尽量减少权限
- 代码公开透明

## Privacy

- Runs entirely locally
- Does not view, record, or save footage
- Does not upload access logs
- No account required
- Uses minimal permissions
- Open-source and transparent


## License

MIT
