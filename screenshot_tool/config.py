"""配置管理:快捷键、保存目录、外观等。

配置文件存放于 %APPDATA%/ScreenShotTool/config.json,
首次运行自动创建默认配置。
"""
import json
import os
from dataclasses import dataclass, asdict, field


CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ScreenShotTool")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class Config:
    # 全局热键:Win32 RegisterHotKey 的修饰符与虚拟键码
    # 默认 Alt+Shift+A (类似微信 Alt+A)
    hotkey_modifiers: int = 0x0001 | 0x0004  # MOD_ALT=0x1 | MOD_SHIFT=0x4
    hotkey_vk: int = 0x41                    # VK_A = 0x41

    # 工具栏外观
    toolbar_color: str = "#2D2D30"
    toolbar_text_color: str = "#FFFFFF"
    accent_color: str = "#FF6B00"           # 选中态/确认按钮色

    # 选区框颜色
    selection_border_color: str = "#FF6B00"
    selection_dim_color_alpha: int = 120    # 选区外遮罩透明度 0-255

    # 放大镜
    magnifier_size: int = 140
    magnifier_zoom: int = 4

    # 默认保存目录 (空串=用户选择)
    save_dir: str = ""

    # 截图后自动复制到剪贴板
    auto_copy_to_clipboard: bool = True

    # 是否最小化到托盘
    minimize_to_tray: bool = True

    # 默认画笔颜色
    default_pen_color: str = "#FF4040"
    default_pen_width: int = 3

    extra: dict = field(default_factory=dict)


def _default_cfg() -> Config:
    return Config()


def load_config() -> Config:
    """读取配置,不存在则创建默认。"""
    if not os.path.exists(CONFIG_FILE):
        cfg = _default_cfg()
        save_config(cfg)
        return cfg
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容字段缺失
        defaults = asdict(_default_cfg())
        defaults.update({k: v for k, v in data.items() if k in defaults})
        defaults.pop("extra", None)
        defaults["extra"] = data.get("extra", {})
        return Config(**defaults)
    except Exception:
        return _default_cfg()


def save_config(cfg: Config) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2, ensure_ascii=False)


# 修饰符映射 (用于 UI 显示与 Win32)
MOD_NAMES = {
    0x0001: "Alt",
    0x0002: "Ctrl",
    0x0004: "Shift",
    0x0008: "Win",
}

# 常用虚拟键码 -> 名称
VK_NAMES = {
    0x41: "A", 0x42: "B", 0x43: "C", 0x44: "D", 0x45: "E",
    0x46: "F", 0x47: "G", 0x48: "H", 0x49: "I", 0x4A: "J",
    0x4B: "K", 0x4C: "L", 0x4D: "M", 0x4E: "N", 0x4F: "O",
    0x50: "P", 0x51: "Q", 0x52: "R", 0x53: "S", 0x54: "T",
    0x55: "U", 0x56: "V", 0x57: "W", 0x58: "X", 0x59: "Y", 0x5A: "Z",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5",
    0x75: "F6", 0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10",
    0x7A: "F11", 0x7B: "F12",
    0x2E: "Delete", 0x2D: "Insert", 0x24: "Home", 0x23: "End",
    0x21: "PageUp", 0x22: "PageDown",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
}


def hotkey_label(cfg: Config) -> str:
    parts = [MOD_NAMES[m] for m in (0x1, 0x2, 0x4, 0x8) if cfg.hotkey_modifiers & m]
    parts.append(VK_NAMES.get(cfg.hotkey_vk, f"VK{cfg.hotkey_vk:02X}"))
    return "+".join(parts)
