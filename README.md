# Companion AI

本地优先的 AI 陪伴桌宠与个人成长助手。它把聊天、长期记忆、训练样本、情绪反馈、文件阅读、屏幕观察和桌面角色整合在一个可持续培养的本地应用中。

项目发布仓库：[LoongSerpent9Realms/companion-ai-release](https://github.com/LoongSerpent9Realms/companion-ai-release)

> 当前版本：`1.0.42`
> 当前提供 Windows 安装包、Linux `.deb`/`.tar.gz` 包和 macOS `.dmg` 包。项目仍在持续开发中，使用前请阅读下方的隐私说明和能力边界。

## 功能概览

- **本地聊天**：通过本地控制台与 Companion AI 对话。
- **长期记忆**：记住用户偏好、重要信息与陪伴习惯，并支持查看、导出和删除。
- **持续培养**：通过问答教学、情绪反馈、行为规则和正负反馈逐步调整回答方式。
- **证据门控自成长**：只用用户明确批准、工具成功或本地规则验证过的样本训练候选 TinyLLM；固定评测与留出样本不混入训练，未通过则不替换当前模型。
- **教学实验室**：从对话、情绪、网页、电脑操作、现实观察和陪伴习惯等路线培养 AI。
- **文件与 OCR**：读取文本、代码、Markdown、HTML、CSV、TSV、JSON；图片支持本地预览和 OCR。
- **现实上下文**：按用户请求获取本机时间、当前前台窗口、屏幕内容和摄像头画面。
- **桌面宠物**：支持置顶、拖动、托盘菜单和根据成长进度切换动作。
- **角色展示**：支持内置 2D 角色，以及可选的 Live2D 和 3D 展示页面。
- **本地模型数据包**：导出记忆、训练样本、反馈、文件摘要和观察记录，方便备份与迁移。
- **可选扩展**：可选接入远程大模型、TTS、OCR、PyTorch 神经网络和插件系统。

## 快速开始

### 方式一：使用 Windows 安装包

从 [Releases](https://github.com/LoongSerpent9Realms/companion-ai-release/releases) 下载最新的 `CompanionAI-Setup-*.exe`，按安装向导完成安装。安装器文件名使用 ASCII，便于在不同系统和镜像服务中下载。

安装后可以从桌面或开始菜单启动：

- `Companion AI`：本地控制台
- `Companion Pet`：桌面宠物
- `Stop Companion AI`：停止本地服务（如安装包提供该入口）

默认数据保存在应用数据目录中，不会写入 GitHub 仓库。

### 方式二：使用 Linux 安装包

从 [Releases](https://github.com/LoongSerpent9Realms/companion-ai-release/releases) 下载 Linux `.deb`/`.tar.gz` 或 Windows 安装包。每次推送匹配 `version.txt` 的 `v*` 标签后，GitHub Actions 会自动构建 Linux、Windows 和 macOS 包，并创建新的 Release。

Debian/Ubuntu：

```bash
sudo dpkg -i companion-ai-*-linux-*.deb
companion-ai
```

通用 Linux 压缩包：

```bash
tar -xzf companion-ai-*-linux-*.tar.gz
cd companion-ai-*-linux-*
./install-user.sh
companion-ai
```

Linux 用户数据默认保存在 `~/.local/share/CompanionAI`；设置 `XDG_DATA_HOME` 后会改用该目录。桌面入口使用系统默认浏览器打开本地控制台。

### 方式三：从源码运行

需要 Python 3.10 或更高版本。建议使用虚拟环境：

```powershell
git clone https://github.com/LoongSerpent9Realms/companion-ai-release.git
cd companion-ai-release
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python app.py
```

启动后打开 [http://127.0.0.1:59137](http://127.0.0.1:59137)。如果系统禁止执行 PowerShell 脚本，也可以直接运行：

```powershell
python app.py
```

桌面宠物模式：

```powershell
python companion_launcher.py --pet
```

### 方式四：使用 macOS 安装包

从 [Releases](https://github.com/LoongSerpent9Realms/companion-ai-release/releases) 下载对应架构的 `.dmg` 文件，将 `CompanionAI.app` 拖入“应用程序”文件夹后启动。当前自动提供：

- `x86_64`：Intel Mac
- `arm64`：Apple Silicon Mac（M1/M2/M3/M4）

macOS 用户数据默认保存在 `~/.local/share/CompanionAI`；设置 `XDG_DATA_HOME` 后会改用该目录。

#### macOS 签名与 Gatekeeper

默认发布的 macOS 包为**未签名构建**，首次启动时 Gatekeeper 会提示无法验证开发者。可用以下任一方式处理：

- 右键点击 `CompanionAI.app`，选择「打开」，在弹出的确认框中再次选择「打开」；
- 或在终端执行 `xattr -dr com.apple.quarantine /Applications/CompanionAI.app`。

如果发布者配置了 Apple Developer ID 签名和公证（需要 `MAC_DEVELOPER_IDENTITY`、`MAC_APPLE_ID`、`MAC_APP_SPECIFIC_PASSWORD`、`MAC_TEAM_ID` 四个密钥），Release 说明中会标注「Developer ID 签名 + 公证」，此类构建可直接启动，无需手动绕过 Gatekeeper。

## 第一次使用

打开控制台后，可以先从教学实验室开始，或在聊天框输入以下命令：

```text
/teach_lab
/accelerate
/apply_pack companion
```

教它一条问答样本：

```text
/teach 当我说我很累 => 先安静陪我一下，再帮我把事情拆成一个很小的下一步。
```

查看和管理本地学习内容：

```text
/memory
/training
/training_samples
/rules
/neural
```

### 小模型自成长：推荐操作顺序

在“设置 → 本地自成长”中完成以下闭环，整个过程默认只在本机运行：

1. 用“真实样本标定”手动填写一条你认可的实际问答并批准。应用不会自动抓取聊天记录作为训练数据。
2. 添加固定能力评测题。可选“包含关键词、正则、完全一致、最大字数、人工确认”五种规则；这些题始终与训练数据隔离。
3. 至少积累 4 条已批准经验后，点击“后台训练候选模型”。界面会显示“准备、训练、留出评测、固定评测、激活”等阶段与进度。
4. 只有候选模型的留出损失合格、且固定评测不低于当前模型时才会激活；每次激活前均保留快照，可在“模型版本”一键恢复。
5. 对生成的心情卡片标注“采用、太亮、太暗、简单些、拒绝”。系统只复用本地配方元数据和种子，不会将图片内容上传或训练图片模型。

### 可选：接入本机 ComfyUI

默认使用内置心情卡片，无需安装任何图像模型。若已在本机启动 ComfyUI，可在“设置 → 本地自成长 → 本地图片后端”启用它：

1. 在 ComfyUI 中将工作流导出为 **API Format** JSON。
2. 填入本机地址（默认 `http://127.0.0.1:8188`）、JSON 文件路径、正向提示词节点 ID；负向提示词与种子节点可选。
3. 点击“保存并测试 ComfyUI”。服务未启动、配置不完整或生成失败时，应用会自动退回内置心情卡片，不会影响聊天和小模型训练。

该桥接只请求你填写的本机地址；生成结果会复制到 Companion AI 的用户数据目录，以便动态页面显示和本地配方反馈。诊断包不包含聊天内容、API 密钥、记忆、图片或审计文本。

主动观察屏幕或摄像头：

```text
/see_screen
/camera
/vision
```

主动获取时间和天气：

```text
/time
/weather Hong Kong
```

## 数据与隐私

Companion AI 采用本地优先设计。聊天记录、长期记忆、训练样本、上传文件摘要、OCR 结果、屏幕观察记录和本地模型数据默认保存在用户设备上。

- 默认服务只监听 `127.0.0.1:59137`，不会自动暴露到局域网。
- 屏幕和摄像头能力需要用户主动触发，默认不会持续采集。
- 闲置探索默认关闭；开启后也只执行本地只读观察，不自动点击、输入或上传文件。
- 天气功能使用 [Open-Meteo](https://open-meteo.com/) 公共接口，仅在查询天气时访问网络。
- 远程大模型、TTS 和其他联网功能均为可选功能，启用前请在设置中确认服务地址和数据处理方式。
- 运行 LAN 模式前请确认当前网络可信，并了解这会让同一局域网设备访问本地服务。

本项目不会帮助绕过登录、付费墙、权限控制、验证码或网站反爬限制。请仅处理你有权访问的内容。

## 运维接口

Companion AI 提供以下本机 HTTP 接口，便于健康检查、备份迁移和局域网安全管理。所有接口默认仅监听 `127.0.0.1`。

### 健康检查

- `GET /api/health` — 返回版本、监听地址、端口、运行模式、数据目录、平台、Python 版本、进程 PID 与存活状态、运行时长。
- 命令行：`python companion_launcher.py --health` — 以 JSON 输出健康报告，不启动服务。适用于启动脚本和监控系统快速判断服务是否可用。

### 备份与迁移

- `GET /api/backup` — 列出数据目录中已有的备份文件。
- `POST /api/backup`（`action: "create"`）— 基于当前数据目录生成带版本号和 SHA256 校验的 `.tar.gz` 备份。备份会排除运行时状态（PID 文件、锁文件、LAN 令牌、更新下载缓存、OCR 缓存等），保证可迁移性。
- `POST /api/backup/restore`（`multipart/form-data`，上限 500MB）— 上传备份归档并安全恢复。恢复前会先解压到临时目录、逐文件校验 SHA256、拒绝路径穿越攻击，校验通过后再写入目标数据目录。

### 局域网配对令牌

启用 LAN 模式后，服务会生成一个配对令牌（pairing token），用于限制非本机设备的写入访问：

- 本机回环请求（`127.0.0.1`、`::1`、`localhost`）无需令牌。
- 局域网设备必须在请求头 `Authorization: Bearer <token>` 或查询参数 `?lan_token=<token>` 中提供正确令牌，否则写入接口会被拒绝。
- 令牌仅在本机 `/api/local_access` 接口（回环访问）中可见。
- `POST /api/local_access`（`action: "regenerate_token"`，仅回环）— 重新生成配对令牌，旧令牌立即失效。

## 能力边界

Companion AI 当前不是通用大语言模型。它主要通过本地规则、记忆、相似度检索、用户教学样本和可选的小型神经网络来工作，因此初始能力有限，需要通过使用和教学逐步培养。

电脑操作目前处于“示范学习和计划生成”阶段：系统可以保存操作步骤并生成可检查的计划，但不会默认控制鼠标和键盘。视觉观察目前主要提供截图、文件信息和 OCR 结果，不能等同于完整的视觉大模型理解。

## 可选组件

基础聊天可以直接运行；以下能力需要额外组件或系统环境：

| 能力 | 说明 |
| --- | --- |
| 本地 OCR | 可使用 Tesseract；也可通过 `/install_ocr` 安装便携式 OCR 后端 |
| 摄像头观察 | 需要 `opencv-python` |
| 神经网络训练 | 需要 PyTorch；支持 CPU，兼容环境下可使用 CUDA 或 DirectML |
| 本地图像生成（可选） | 内置心情卡片无需额外依赖；ComfyUI 需用户本机启动服务并提供 API Format workflow |
| 远程大模型 | 在设置中配置兼容的 API 地址和密钥 |
| Live2D | 将包含 `.model3.json` 的模型放入 `data/live2d/` 或通过界面导入 |
| 3D 角色 | 通过本地 3D 页面导入兼容模型 |

## 常用脚本

| 文件 | 用途 |
| --- | --- |
| `app.py` | 启动本地控制台和 HTTP 服务 |
| `companion_launcher.py` | 启动桌面宠物或角色展示窗口 |
| `Launch Companion AI.ps1` | 启动本地 AI 服务 |
| `Launch Companion AI LAN.ps1` | 显式开启局域网访问 |
| `Install Companion Desktop Pet.cmd` | 启动桌面宠物安装器 |
| `build_exe.py` | 构建 PyInstaller 应用 |
| `build_release.ps1` | 构建并签名 Windows 安装包 |
| `build_linux.sh` | 构建 Linux `.deb` 和 `.tar.gz` 包 |
| `build_macos.sh` | 构建 macOS `.app` 和 `.dmg` 包 |

## 开发与构建

源码运行：

```powershell
python app.py
```

运行测试：

```powershell
python -m unittest discover -p "test_*.py"
```

构建 Windows 发布包需要 Python、PyInstaller、NSIS；签名发布还需要 Windows SDK 的 `signtool.exe` 和代码签名证书：

```powershell
.\build_release.ps1
```

没有签名环境时可跳过签名，仅用于本地测试：

```powershell
.\build_release.ps1 -SkipSigning
```

构建 Linux 包需要 Linux、Python 3、`python3-tk`、`dpkg-deb` 和网络连接：

```bash
chmod +x build_linux.sh packaging/linux/*.sh packaging/linux/companion-ai
./build_linux.sh
```

输出文件位于 `dist/linux/`：

```text
companion-ai-<version>-linux-<arch>.deb
companion-ai-<version>-linux-<arch>.tar.gz
```

构建 macOS 包需要在 macOS 上运行，并需要 Python 3、Xcode Command Line Tools 和网络连接：

```bash
chmod +x build_macos.sh
./build_macos.sh
```

输出文件位于 `dist/macos/`：

```text
companion-ai-<version>-macos-x86_64.dmg
companion-ai-<version>-macos-arm64.dmg
```

### 自动发布

更新 `version.txt` 后提交并推送对应标签：

```bash
git tag v1.0.43
git push origin main v1.0.43
```

标签必须与 `version.txt` 完全一致。工作流会等待 Linux、Windows 和 macOS 构建都成功后，自动创建 GitHub Release 并上传全部安装包、聚合 `SHA256SUMS.txt` 校验文件和对应版本的 `CHANGELOG-v<version>.md`。手动运行工作流只构建并上传构件，不会创建 Release。

发布说明会自动包含：

- 三平台安装包清单；
- 聚合 SHA256 校验文件下载与验证指引；
- 各平台签名状态（Windows 未签名；macOS 根据密钥配置显示签名/公证状态或未签名提示）；
- 已知限制。

如需启用 macOS Developer ID 签名和公证，在仓库 Secrets 中配置以下四个值：

- `MAC_DEVELOPER_IDENTITY` — 形如 `Developer ID Application: Your Name (TEAMID)`
- `MAC_APPLE_ID` — Apple ID 邮箱
- `MAC_APP_SPECIFIC_PASSWORD` — 应用专用密码（非 Apple ID 密码）
- `MAC_TEAM_ID` — 开发者团队 ID

未配置这些 Secret 时，macOS 构建为未签名包，Release 说明中会标注 Gatekeeper 绕过方法。

## 项目结构

```text
app.py                    本地 Web 控制台与主要服务
companion_launcher.py     桌面宠物启动器
memory_layer.py           长期记忆
hybrid_chat.py            本地对话与检索
dialogue_skills.py        对话技能与行为规则
desktop_pet.py            桌面宠物窗口
live2d_viewer.html        Live2D 查看器
viewer_3d.html            3D 查看器
plugins/                  插件示例与模板
static/                   前端静态资源
release_assets/           发布说明与安装包资源
```

用户数据目录可能包含聊天、记忆、训练样本、上传文件和观察记录，请不要将个人数据目录提交到公开仓库。

## 许可证

软件使用条款见 [LICENSE.txt](LICENSE.txt)。安装或使用本软件前，请阅读其中的许可、隐私、责任限制和知识产权条款。

## 反馈与贡献

欢迎通过 [GitHub Issues](https://github.com/LoongSerpent9Realms/companion-ai-release/issues) 反馈问题或提出建议。提交问题时请附上：

- 操作系统和 Python 版本
- Companion AI 版本
- 复现步骤和错误信息
- 是否启用了 OCR、摄像头、远程大模型或其他可选组件

请先移除聊天记录、访问令牌、API 密钥、个人文件路径和其他敏感信息。
