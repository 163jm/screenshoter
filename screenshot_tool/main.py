"""主程序:系统托盘 + 全局热键 + 截图窗口调度。

启动后驻留托盘,按全局热键唤起截图。
"""
import sys
import ctypes

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QFont
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox,
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QDialog,
    QDialogButtonBox, QFormLayout, QComboBox, QCheckBox, QSpinBox
)

from .config import Config, load_config, save_config, hotkey_label, MOD_NAMES, VK_NAMES
from .hotkey import HotkeyWindow
from .capture import CaptureWindow


# MOD 值 -> 显示名
def mod_options():
    return [(0x0001, "Alt"), (0x0002, "Ctrl"), (0x0004, "Shift"), (0x0008, "Win")]


def vk_options():
    return [(v, n) for v, n in VK_NAMES.items()]


def make_app_icon() -> QIcon:
    """绘制应用图标(避免外部资源)。"""
    px = QPixmap(64, 64)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    # 圆角背景
    p.setBrush(QBrush(QColor("#FF6B00")))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    # 剪刀/相机图标(简化为相机)
    p.setBrush(QBrush(QColor("#FFFFFF")))
    p.drawRoundedRect(16, 22, 32, 22, 4, 4)
    p.drawEllipse(32, 33, 10, 10)
    p.setBrush(QBrush(QColor("#FF6B00")))
    p.drawEllipse(32, 33, 4, 4)
    # 顶部闪光
    p.setBrush(QBrush(QColor("#FFFFFF")))
    p.drawRoundedRect(26, 16, 12, 4, 2, 2)
    p.end()
    return QIcon(px)


class SettingsDialog(QDialog):
    """设置对话框:快捷键、默认保存目录。"""
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.config = config
        self.setMinimumWidth(380)
        self._build()

    def _build(self):
        form = QFormLayout(self)

        # 修饰符 (多选通过 4 个 checkbox)
        mod_box = QWidget()
        mod_layout = QHBoxLayout(mod_box)
        mod_layout.setContentsMargins(0, 0, 0, 0)
        self.mod_checks = {}
        for val, name in mod_options():
            cb = QCheckBox(name)
            cb.setChecked(bool(self.config.hotkey_modifiers & val))
            mod_layout.addWidget(cb)
            self.mod_checks[val] = cb
        form.addRow("修饰键 (可组合):", mod_box)

        # 主键
        self.vk_combo = QComboBox()
        for v, n in vk_options():
            self.vk_combo.addItem(n, v)
        idx = self.vk_combo.findData(self.config.hotkey_vk)
        if idx >= 0:
            self.vk_combo.setCurrentIndex(idx)
        form.addRow("主键:", self.vk_combo)

        # 默认画笔颜色
        self.color_label = QLabel(self.config.default_pen_color)
        self.color_label.setStyleSheet(
            f"background:{self.config.default_pen_color};color:white;padding:6px;"
        )
        color_btn = QPushButton("选择颜色")
        color_btn.clicked.connect(self._pick_color)
        cb = QHBoxLayout()
        cb.addWidget(self.color_label)
        cb.addWidget(color_btn)
        cb_w = QWidget(); cb_w.setLayout(cb)
        form.addRow("默认画笔颜色:", cb_w)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 20)
        self.width_spin.setValue(self.config.default_pen_width)
        form.addRow("默认线宽:", self.width_spin)

        self.auto_copy = QCheckBox("完成后自动复制到剪贴板")
        self.auto_copy.setChecked(self.config.auto_copy_to_clipboard)
        form.addRow("", self.auto_copy)

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _pick_color(self):
        from PyQt5.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.config.default_pen_color), self)
        if c.isValid():
            self.config.default_pen_color = c.name()
            self.color_label.setText(c.name())
            self.color_label.setStyleSheet(f"background:{c.name()};color:white;padding:6px;")

    def apply_to_config(self) -> Config:
        cfg = self.config
        mods = 0
        for val, cb in self.mod_checks.items():
            if cb.isChecked():
                mods |= val
        if mods == 0:
            mods = 0x0001 | 0x0004  # 默认 Alt+Shift
        cfg.hotkey_modifiers = mods
        cfg.hotkey_vk = self.vk_combo.currentData()
        cfg.default_pen_color = self.color_label.text()
        cfg.default_pen_width = self.width_spin.value()
        cfg.auto_copy_to_clipboard = self.auto_copy.isChecked()
        return cfg


class TrayApp(QObject):
    """托盘应用主控。"""
    def __init__(self, argv):
        super().__init__()
        self.app = QApplication.instance() or QApplication(argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.config = load_config()
        self.icon = make_app_icon()
        self.app.setWindowIcon(self.icon)

        # 系统托盘
        self.tray = QSystemTrayIcon(self.icon, self.app)
        self.tray.setToolTip(f"截屏工具 (热键: {hotkey_label(self.config)})")
        self._build_tray_menu()
        self.tray.show()

        # 全局热键
        self.hotkey_win = HotkeyWindow(
            self.config.hotkey_modifiers, self.config.hotkey_vk
        )
        self.hotkey_win.triggered.connect(self.start_capture)
        if not self.hotkey_win.register():
            self.tray.showMessage(
                "截屏工具",
                f"注册热键 {hotkey_label(self.config)} 失败,可能已被占用。\n请在设置中更换。",
                QSystemTrayIcon.Warning,
                5000,
            )

        self.capture_window: CaptureWindow = None

    def _build_tray_menu(self):
        menu = QMenu()
        act_capture = QAction("截图", menu)
        act_capture.triggered.connect(self.start_capture)
        menu.addAction(act_capture)

        act_settings = QAction("设置...", menu)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        # 双击托盘触发截图
        if reason == QSystemTrayIcon.DoubleClick:
            self.start_capture()

    def start_capture(self):
        if self.capture_window is not None:
            return  # 已在截图中
        self.capture_window = CaptureWindow(self.config)
        self.capture_window.finished.connect(self._on_finished)
        self.capture_window.canceled.connect(self._on_canceled)
        self.capture_window.start_capture()

    def _on_finished(self, pix):
        self.capture_window = None

    def _on_canceled(self):
        self.capture_window = None

    def open_settings(self):
        dlg = SettingsDialog(self.config)
        if dlg.exec_() == QDialog.Accepted:
            cfg = dlg.apply_to_config()
            save_config(cfg)
            self.config = cfg
            # 重新注册热键
            self.hotkey_win.unregister()
            self.hotkey_win = HotkeyWindow(cfg.hotkey_modifiers, cfg.hotkey_vk)
            self.hotkey_win.triggered.connect(self.start_capture)
            if not self.hotkey_win.register():
                self.tray.showMessage(
                    "截屏工具",
                    f"新热键 {hotkey_label(cfg)} 注册失败,可能被占用。",
                    QSystemTrayIcon.Warning, 5000,
                )
            self.tray.setToolTip(f"截屏工具 (热键: {hotkey_label(cfg)})")
            self.tray.showMessage(
                "截屏工具", "设置已保存", QSystemTrayIcon.Information, 2000
            )

    def quit(self):
        if self.hotkey_win:
            self.hotkey_win.unregister()
        self.tray.hide()
        self.app.quit()

    def run(self) -> int:
        # 首次启动提示
        QTimer.singleShot(800, lambda: self.tray.showMessage(
            "截屏工具已启动",
            f"按 {hotkey_label(self.config)} 截图,双击托盘图标也可触发。",
            QSystemTrayIcon.Information, 5000,
        ))
        return self.app.exec_()


def main():
    # 高 DPI 支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = TrayApp(sys.argv)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
