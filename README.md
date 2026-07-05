# Windows 截屏工具 (ScreenShotTool)

类似 Windows 微信截屏 (Alt+A) 功能的桌面截图程序,基于 Python + PyQt5 实现,
打包为单文件 `ScreenShotTool.exe`,无需 Python 环境即可运行。

## 功能

- **全局快捷键** 唤起截图 (默认 `Alt+Shift+A`,可在设置中修改)
- **拖拽选区** + 实时显示选区尺寸
- **放大镜** 跟随鼠标,显示当前像素 RGB 与坐标
- **完整标注工具栏**
  - 矩形 `R` / 椭圆 `O` / 箭头 `A` / 画笔 `P` / 马赛克 `M` / 文字 `T`
  - 颜色选择 / 线宽调节
  - 撤销 `Ctrl+Z`
- **多显示器** 支持 (跨屏选区)
- **复制到剪贴板** / **保存为 PNG/JPG**
- **系统托盘** 驻留,双击托盘也可触发截图

## 快捷键

| 操作 | 快捷键 |
|------|--------|
| 触发截图 | `Alt+Shift+A` (可改) |
| 撤销标注 | `Ctrl+Z` |
| 保存为文件 | `Ctrl+S` |
| 确认 (复制到剪贴板) | `Enter` |
| 取消 | `Esc` / `鼠标右键` |

## 目录结构

```
.
├── screenshot_tool/         # 源代码包
│   ├── __init__.py
│   ├── __main__.py          # 入口: python -m screenshot_tool
│   ├── main.py              # 托盘 + 热键调度 + 设置对话框
│   ├── hotkey.py            # Win32 RegisterHotKey 全局热键
│   ├── capture.py           # 全屏截图窗口 + 选区 + 放大镜 + 标注
│   ├── toolbar.py           # 标注工具栏
│   ├── annotations.py       # 标注图形数据结构
│   └── config.py            # 配置管理
├── requirements.txt         # PyQt5 + pyinstaller
├── build.spec               # PyInstaller 打包配置 (单文件 exe)
├── .github/workflows/build.yml   # GitHub Actions 自动构建
└── README.md
```

## 本地构建

需要 Python 3.10+。

```powershell
pip install -r requirements.txt
pyinstaller build.spec --noconfirm
# 产物: dist/ScreenShotTool.exe
```

直接运行源码 (开发调试):

```powershell
python -m screenshot_tool
```

## GitHub Actions 自动构建

仓库已配置 `.github/workflows/build.yml`,有两种触发方式:

### 方式一: 打 Tag 自动发布 Release

```bash
git tag v1.0.0
git push origin v1.0.0
```

Action 会:
1. 在 `windows-latest` 上安装依赖并 PyInstaller 打包
2. 做一次冒烟测试 (启动 3 秒确认无崩溃)
3. 上传构建产物 (artifact)
4. 创建 GitHub Release,附带 `ScreenShotTool-x64.exe`

### 方式二: 手动触发

在仓库的 **Actions** 标签页 -> 选择 **Build Windows EXE** workflow ->
**Run workflow**,可只构建 (artifact) 或同时发布 Release。

构建完成后,在 Actions 运行结果页底部 **Artifacts** 区下载 `ScreenShotTool-windows-x64`。

## 配置文件

首次运行后,配置保存在:

```
%APPDATA%\ScreenShotTool\config.json
```

包含:热键、画笔颜色、线宽、保存目录等。可手动编辑或通过托盘右键 -> **设置** 修改。

## 技术说明

- **全局热键**: 使用 Win32 `RegisterHotKey` + `QWidget.nativeEvent` 捕获 `WM_HOTKEY`,
  无需第三方热键库,不依赖管理员权限。
- **截图**: `QScreen.grabWindow(0)` 抓取虚拟桌面,天然支持多屏。
- **图标**: 全部用 `QPainter` 现场绘制,无外部图片资源,体积小。
- **打包**: `pyinstaller --windowed` 单文件模式,不弹控制台。

## 已知限制

- 高 DPI 缩放下放大镜像素取值已处理,极端缩放比例可能略偏移
- 文字工具使用对话框输入,而非选区内直接编辑 (后续可优化)
