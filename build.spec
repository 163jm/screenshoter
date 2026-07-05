# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置:生成单文件 ScreenShotTool.exe。

打包命令:
    pyinstaller build.spec --noconfirm
产物:
    dist/ScreenShotTool.exe

注意: PyInstaller 6.x 自带 hook-PyQt5.py 会自动收集 Qt 插件、
translations、bin 等数据文件,不需要手动 collect_data_files。
手动追加 2 元组会破坏 6.x 要求的 3 元组 TOC 格式。
"""

a = Analysis(
    ['screenshot_tool/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # 确保子模块被收集 (作为包内引用)
        'screenshot_tool',
        'screenshot_tool.main',
        'screenshot_tool.config',
        'screenshot_tool.hotkey',
        'screenshot_tool.capture',
        'screenshot_tool.toolbar',
        'screenshot_tool.annotations',
        # PyQt5 sip 桥接
        'PyQt5.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'pydoc',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ScreenShotTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # 使用 windowed 模式:不弹黑框控制台
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon 由运行时绘制,留空即可;如有 .ico 可在此指定:
    # icon='assets/app.ico',
)
