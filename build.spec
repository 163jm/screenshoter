# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置:生成单文件 ScreenShotTool.exe。

打包命令:
    pyinstaller build.spec
产物:
    dist/ScreenShotTool.exe
"""
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
    ['screenshot_tool/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # 确保子模块被收集
        'screenshot_tool',
        'screenshot_tool.main',
        'screenshot_tool.config',
        'screenshot_tool.hotkey',
        'screenshot_tool.capture',
        'screenshot_tool.toolbar',
        'screenshot_tool.annotations',
        # PyQt5 插件
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
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 收集 PyQt5 数据文件 (插件、translations 等)
a.datas += collect_data_files('PyQt5')

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
