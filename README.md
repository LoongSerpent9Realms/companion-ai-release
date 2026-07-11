# Companion AI

本地优先的 AI 陪伴桌宠与个人成长助手。它把聊天、长期记忆、训练样本、情绪反馈、文件阅读、屏幕观察和桌面角色整合在一个可持续培养的本地应用中。

项目发布仓库：[LoongSerpent9Realms/companion-ai-release](https://github.com/LoongSerpent9Realms/companion-ai-release)

> 当前版本：`1.0.42`
> 当前提供 Windows 安装包和 Linux `.deb`/`.tar.gz` 包。项目仍在持续开发中，使用前请阅读下方的隐私说明和能力边界。

## 功能概览

- **本地聊天**：通过本地控制台与 Companion AI 对话。
- **长期记忆**：记住用户偏好、重要信息与陪伴习惯，并支持查看、导出和删除。
- **持续培养**：通过问答教学、情绪反馈、行为规则和正负反馈逐步调整回答方式。
- **教学实验室**：从对话、情绪、网页、电脑操作、现实观察和陪伴习惯等路线培养 AI。
- **文件与 OCR**：读取文本、代码、Markdown、HTML、CSV、TSV、JSON；图片支持本地预览和 OCR。
- **现实上下文**：按用户请求获取本机时间、当前前台窗口、屏幕内容和摄像头画面。
- **桌面宠物**：支持置顶、拖动、托盘菜单和根据成长进度切换动作。
- **角色展示**：支持内置 2D 角色，以及可选的 Live2D 和 3D 展示页面。
- **本地模型数据包**：导出记忆、训练样本、反馈、文件摘要和观察记录，方便备份与迁移。
- **可选扩展**：可选接入远程大模型、TTS、OCR、PyTorch 神经网络和插件系统。

## 快速开始

### 方式一：使用 Windows 安装包

从 [Releases](https://github.com/LoongSerpent9Realms/companion-ai-release/releases) 下载最新的 `CompanionAI-Setup-*.exe`，按安装向导完成安装。

安装后可以从桌面或开始菜单启动：

- `Companion AI`：本地控制台
- `Companion Pet`：桌面宠物
- `Stop Companion AI`：停止本地服务（如安装包提供该入口）

默认数据保存在应用数据目录中，不会写入 GitHub 仓库。

### 方式二：使用 Linux 安装包

从 [Actions](https://github.com/LoongSerpent9Realms/companion-ai-release/actions) 的 `Linux package` 工作流下载构件，或从 [Releases](https://github.com/LoongSerpent9Realms/companion-ai-release/releases) 下载发布包。

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
