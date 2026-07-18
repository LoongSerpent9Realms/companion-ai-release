# 智能伙伴 v1.0.42

本次发布聚焦跨平台安装可靠性、运维可观测性、局域网安全和数据迁移能力，覆盖 Linux、Windows 和 macOS 三平台。

## 主要更新

### P1：Linux 安装布局与启动入口修复

- 重写 Linux 启动器 `packaging/linux/companion-ai`，支持三种安装布局的自动探测：
  1. `.deb` 安装布局（`/usr/bin` → `/opt/companion-ai`）
  2. 通用 `tar.gz` 解压布局（`<pkg>/usr/bin` → `<pkg>/opt/companion-ai`）
  3. 便携解压布局（脚本同目录下的 `CompanionAI/`）
- 探测失败时打印全部候选路径并退出，便于排查。
- 使用 `set -eu`、`CDPATH= cd --` 保证 POSIX 安全的路径解析。

### P2：跨平台启动健康检查

- 新增 `GET /api/health` 接口，返回版本、监听地址、端口、运行模式、数据目录、平台、Python 版本、Web/桌宠进程 PID 与存活状态、运行时长。
- 新增 `companion_launcher.py --health` 命令行参数，以 JSON 输出健康报告后退出，不启动服务。
- 跨平台 PID 存活检测：POSIX 使用 `os.kill(pid, 0)`，Windows 使用 `tasklist` 过滤。

### P3：核心单元测试扩充

- 新增 `test_core_runtime.py`，共 28 项测试，覆盖：
  - 数据目录解析与旧目录迁移（6 项）
  - 版本号比较与升级判断（3 项）
  - 上传大小限制与缺字段错误（2 项）
  - 局域网状态接口与进程健康（2 项）
  - LAN 令牌稳定性、重置、回环识别、非回环隐藏（5 项）
  - 远程大模型配置脱敏（长 key 截断、短 key 全掩码、空 key 未配置）（3 项）
  - 模型数据包导出结构与统计完整性（2 项）
  - 备份创建、瞬态排除、往返一致性、篡改拒绝、缺文件拒绝（5 项）
- 测试通过 monkeypatch 模块级常量实现隔离，避免 `importlib.reload` 副作用。

### P4：局域网访问安全加固

- 启用 LAN 模式后自动生成配对令牌（`secrets.token_urlsafe(32)`），持久化到数据目录。
- 非回环请求必须通过 `Authorization: Bearer <token>` 请求头或 `?lan_token=<token>` 查询参数提供正确令牌，否则写入接口被拒绝。
- 令牌比较使用 `hmac.compare_digest` 防止时序攻击。
- 回环请求（`127.0.0.1`、`::1`、`localhost`）和本地模式始终免认证。
- 令牌仅在回环访问 `/api/local_access` 时返回，非回环响应不包含令牌字段。
- 新增 `POST /api/local_access`（`action: "regenerate_token"`，仅回环）用于重新生成令牌。

### P5：本地备份与迁移

- 新增 `POST /api/backup`（`action: "create"`）：基于当前数据目录生成带版本号和 SHA256 校验的 `.tar.gz` 备份。
- 备份归档包含 `manifest.json`，记录每个文件的相对路径和 SHA256。
- 自动排除运行时状态：`backups/`、`updates/`、`ocr/`、`runtime/` 目录，`.pid`/`.lock`/`.tmp`/`.bak` 后缀，以及 `lan_token.json`、`realtime_chat.json` 等瞬态文件。
- 新增 `POST /api/backup/restore`（`multipart/form-data`，上限 500MB）：上传归档后先解压到临时目录，逐文件校验 SHA256，拒绝绝对路径和 `..` 路径穿越，校验通过后再写入目标数据目录。
- 新增 `GET /api/backup` 列出已有备份文件。

### P6：macOS 发布可信度

- `build_macos.sh` 新增可选 Developer ID 代码签名：
  - 由 `MAC_DEVELOPER_IDENTITY` 环境变量激活。
  - 先签名内嵌 `.dylib`/`.so`/可执行文件，再 `codesign --deep --force --options runtime --timestamp` 签名 `.app`。
  - 使用 Hardened Runtime（`--options runtime`）满足公证要求。
  - 签名后用 `codesign --verify --strict --verbose=2` 验证。
- 新增可选 Apple 公证与 Stapling：
  - 由 `MAC_APPLE_ID`、`MAC_APP_SPECIFIC_PASSWORD`、`MAC_TEAM_ID` 三个环境变量激活。
  - 使用 `xcrun notarytool submit --wait --timeout 30m` 提交 DMG 并等待结果。
  - 公证通过后用 `xcrun stapler staple` 装订票据，使离线 Gatekeeper 检查通过。
- 未签名构建输出清晰的 Gatekeeper 绕过指引：`xattr -dr com.apple.quarantine /Applications/CompanionAI.app`。

### P7：发布流程与文档审计

- `.github/workflows/release.yml` 为三平台分别生成 SHA256 校验文件，并在 Release 作业中聚合为单一 `SHA256SUMS.txt`。
- macOS 构建作业通过 Secrets 传递四个签名/公证密钥，构建后提取签名状态写入 `sign-status-*.txt`。
- Release 作业自动生成发布说明，包含安装包清单、SHA256 验证指引、各平台签名状态表和已知限制。
- 对应版本的 `CHANGELOG-v<version>.md` 自动随 Release 资产上传。
- README 新增「运维接口」章节（健康检查、备份迁移、LAN 配对令牌）和「macOS 签名与 Gatekeeper」说明。

## 安装包

- Windows：`CompanionAI-Setup-v1.0.42.exe`（未签名，SmartScreen 可能警告）
- Linux：`companion-ai-1.0.42-linux-x86_64.deb`、`companion-ai-1.0.42-linux-x86_64.tar.gz`
- macOS：`companion-ai-1.0.42-macos-x86_64.dmg`、`companion-ai-1.0.42-macos-arm64.dmg`（默认未签名；配置签名密钥后为 Developer ID 签名 + 公证）

SHA256 校验请使用 Release 资产中的 `SHA256SUMS.txt`：

```bash
sha256sum -c SHA256SUMS.txt
```

## 已知限制

- Windows 安装包未进行代码签名，SmartScreen 可能显示警告，可点击「仍要运行」继续。
- macOS 默认为未签名构建，首次启动需右键 → 打开，或使用 `xattr -dr com.apple.quarantine /Applications/CompanionAI.app`。
- Linux 包依赖系统 Python 3.10+，部分功能（OCR、摄像头、神经网络训练）需要额外安装对应依赖。
- 备份恢复会覆盖目标数据目录中的同名文件，恢复前建议先创建当前状态的备份。
