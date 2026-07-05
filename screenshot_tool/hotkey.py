"""全局热键:基于 Win32 RegisterHotKey + QWidget.nativeEvent。

不依赖第三方库,稳定性高,不需要管理员权限。
热键消息会发送给注册它的线程,因此必须在主线程的窗口上注册。
"""
import ctypes
from ctypes import wintypes

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Win32 常量
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

# RegisterHotKey(HWND hWnd, int id, UINT fsModifiers, UINT vk)
user32.RegisterHotKey.argtypes = [wintypes.HWND, wintypes.INT, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, wintypes.INT]
user32.UnregisterHotKey.restype = wintypes.BOOL


class HotkeyWindow(QWidget):
    """隐藏窗口,用于接收全局热键消息。"""

    triggered = pyqtSignal()

    HOTKEY_ID = 0x8001  # 自定义热键 ID

    def __init__(self, modifiers: int, vk: int, parent=None):
        super().__init__(parent)
        # 不可见窗口
        self.setWindowFlags(0)  # 无装饰
        self.resize(0, 0)
        self.move(-10000, -10000)
        self.show()
        self.hide()
        self._mods = modifiers
        self._vk = vk
        self._registered = False

    def register(self) -> bool:
        """注册全局热键。返回是否成功。"""
        if self._registered:
            self.unregister()
        # 加 MOD_NOREPEAT 避免长按重复触发
        mods = self._mods | MOD_NOREPEAT
        hwnd = int(self.winId())
        ok = bool(user32.RegisterHotKey(hwnd, self.HOTKEY_ID, mods, self._vk))
        self._registered = ok
        return ok

    def unregister(self) -> None:
        if self._registered:
            hwnd = int(self.winId())
            user32.UnregisterHotKey(hwnd, self.HOTKEY_ID)
            self._registered = False

    def nativeEvent(self, eventType, message):
        # PyQt5 在 Windows 上 message 是 sip.voidptr(可转为 int),
        # 指向 MSG 结构。某些版本是 (ptr,) 元组。
        try:
            ptr = message[0] if isinstance(message, (tuple, list)) else message
            ptr = int(ptr)
            msg = wintypes.MSG.from_address(ptr)
            if msg.message == WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                self.triggered.emit()
                return True, 0
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        self.unregister()
        super().closeEvent(event)
