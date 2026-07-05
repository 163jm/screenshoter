"""标注工具栏:类似微信截图的工具条。

布局:
  [矩形][椭圆][箭头][画笔][马赛克][文字][撤销]  |  [颜色][线宽]  |  [保存][确认][取消]
"""
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRect, QPoint
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPixmap, QIcon, QAction,
    QPainterPath, QPolygonF, QPointF,
)
from PyQt5.QtWidgets import (
    QWidget, QToolButton, QHBoxLayout, QPushButton, QColorDialog,
    QLabel, QSpinBox, QFrame, QSizePolicy,
)

from .annotations import ToolType


def make_tool_icon(tool: ToolType, color: QColor = QColor("#FFFFFF")) -> QPixmap:
    """绘制工具图标(避免外部资源)。"""
    px = QPixmap(20, 20)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color, 1.6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if tool == ToolType.RECT:
        p.drawRect(3, 4, 14, 12)
    elif tool == ToolType.ELLIPSE:
        p.drawEllipse(3, 4, 14, 12)
    elif tool == ToolType.ARROW:
        p.drawLine(4, 16, 16, 4)
        # 箭头
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        poly = QPolygonF([QPointF(16, 4), QPointF(10, 4), QPointF(16, 10)])
        p.drawPolygon(poly)
    elif tool == ToolType.PEN:
        path = QPainterPath()
        path.moveTo(3, 16)
        path.cubicTo(6, 6, 12, 18, 17, 5)
        p.drawPath(path)
    elif tool == ToolType.MOSAIC:
        # 方格
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        for x in range(3, 17, 4):
            for y in range(3, 17, 4):
                p.drawRect(x, y, 3, 3)
    elif tool == ToolType.TEXT:
        font = QFont("Arial", 11, QFont.Bold)
        p.setFont(font)
        p.setPen(QPen(color))
        p.drawText(QRect(0, 0, 20, 20), Qt.AlignCenter, "T")
    elif tool == ToolType.ERASER:
        # 撤销图标:左拐箭头
        path = QPainterPath()
        path.moveTo(15, 5)
        path.lineTo(6, 5)
        path.lineTo(6, 11)
        path.lineTo(15, 11)
        p.drawPath(path)
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        poly = QPolygonF([QPointF(6, 5), QPointF(2, 8), QPointF(6, 11)])
        p.drawPolygon(poly)
    p.end()
    return px


class ColorButton(QToolButton):
    """显示当前颜色的色块按钮。"""
    color_changed = pyqtSignal(QColor)

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(28, 28)
        self.setToolTip("颜色")
        self.clicked.connect(self._pick)

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, "选择颜色")
        if c.isValid():
            self._color = c
            self.update()
            self.color_changed.emit(c)

    def color(self) -> QColor:
        return QColor(self._color)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor("#888"), 1))
        p.setBrush(QBrush(self._color))
        p.drawRoundedRect(2, 2, self.width() - 4, self.height() - 4, 4, 4)


class ToolbarButton(QToolButton):
    """工具栏按钮。"""
    def __init__(self, icon_px: QPixmap, tooltip: str, checkable: bool = True, parent=None):
        super().__init__(parent)
        self.setIcon(QIcon(icon_px))
        self.setIconSize(QSize(20, 20))
        self.setFixedSize(34, 30)
        self.setToolTip(tooltip)
        self.setCheckable(checkable)
        self._checked = False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.isChecked():
            p.setBrush(QBrush(QColor("#3F3F46")))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 4, 4)
        elif self.underMouse():
            p.setBrush(QBrush(QColor("#3A3A3F")))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 4, 4)
        # 图标
        self.icon().paint(p, 6, 4, self.width() - 12, self.height() - 8)


class Toolbar(QFrame):
    """底部工具栏。"""
    TOOL_RECT = "rect"
    TOOL_PEN_COLOR_CHANGED = pyqtSignal(QColor)
    TOOL_PEN_WIDTH_CHANGED = pyqtSignal(int)
    TOOL_CHANGED = pyqtSignal(object)  # ToolType or None
    UNDO_REQUESTED = pyqtSignal()
    SAVE_REQUESTED = pyqtSignal()
    CONFIRM_REQUESTED = pyqtSignal()
    CANCEL_REQUESTED = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CaptureToolbar")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedSize(440, 44)
        self.setStyleSheet("""
            #CaptureToolbar {
                background: #2D2D30;
                border: 1px solid #1E1E1E;
                border-radius: 6px;
            }
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        # 工具按钮
        self.tool_buttons = {}
        tools = [
            (ToolType.RECT,   "矩形 (R)"),
            (ToolType.ELLIPSE,"椭圆 (O)"),
            (ToolType.ARROW,  "箭头 (A)"),
            (ToolType.PEN,     "画笔 (P)"),
            (ToolType.MOSAIC,  "马赛克 (M)"),
            (ToolType.TEXT,    "文字 (T)"),
        ]
        for t, tip in tools:
            btn = ToolbarButton(make_tool_icon(t), tip)
            btn.clicked.connect(lambda _=False, tool=t: self._select_tool(tool))
            layout.addWidget(btn)
            self.tool_buttons[t] = btn

        # 撤销
        undo_btn = ToolbarButton(make_tool_icon(ToolType.ERASER), "撤销 (Ctrl+Z)", checkable=False)
        undo_btn.clicked.connect(self.UNDO_REQUESTED.emit)
        layout.addWidget(undo_btn)

        layout.addSpacing(8)
        # 分隔
        sep = QFrame(); sep.setFixedWidth(1); sep.setStyleSheet("background:#3F3F46;")
        layout.addWidget(sep)
        layout.addSpacing(4)

        # 颜色
        self.color_btn = ColorButton(QColor("#FF4040"))
        self.color_btn.color_changed.connect(self.TOOL_PEN_COLOR_CHANGED.emit)
        layout.addWidget(self.color_btn)

        # 线宽
        lw_label = QLabel("线宽")
        lw_label.setStyleSheet("color:#DDD; background:transparent;")
        lw_label.setFixedHeight(20)
        layout.addWidget(lw_label)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 20)
        self.width_spin.setValue(3)
        self.width_spin.setFixedWidth(46)
        self.width_spin.setStyleSheet(
            "QSpinBox{background:#3F3F46;color:#FFF;border:none;border-radius:3px;padding:0 4px;}"
            "QSpinBox::up-button,QSpinBox::down-button{width:12px;}"
        )
        self.width_spin.valueChanged.connect(self.TOOL_PEN_WIDTH_CHANGED.emit)
        layout.addWidget(self.width_spin)

        layout.addSpacing(8)
        sep2 = QFrame(); sep2.setFixedWidth(1); sep2.setStyleSheet("background:#3F3F46;")
        layout.addWidget(sep2)
        layout.addSpacing(4)

        # 操作按钮
        self.save_btn = self._action_btn("保存", "#3F3F46")
        self.save_btn.clicked.connect(self.SAVE_REQUESTED.emit)
        layout.addWidget(self.save_btn)

        self.confirm_btn = self._action_btn("✔ 完成", "#FF6B00")
        self.confirm_btn.clicked.connect(self.CONFIRM_REQUESTED.emit)
        layout.addWidget(self.confirm_btn)

        self.cancel_btn = self._action_btn("✘ 取消", "#3F3F46")
        self.cancel_btn.clicked.connect(self.CANCEL_REQUESTED.emit)
        layout.addWidget(self.cancel_btn)

        layout.addStretch(0)

        # 默认选中矩形
        self._select_tool(ToolType.RECT)

    def _action_btn(self, text: str, bg: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(30)
        b.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: white; border: none;
                border-radius: 4px; padding: 0 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {self._lighten(bg)}; }}
        """)
        return b

    def _lighten(self, hexcolor: str) -> str:
        c = QColor(hexcolor); c = c.lighter(120); return c.name()

    def _select_tool(self, tool: ToolType):
        for t, b in self.tool_buttons.items():
            b.setChecked(t == tool)
        self.TOOL_CHANGED.emit(tool)

    def set_pen_color(self, color: QColor):
        self.color_btn._color = color
        self.color_btn.update()

    def set_pen_width(self, w: int):
        self.width_spin.setValue(w)

    def clear_tool_selection(self):
        for b in self.tool_buttons.values():
            b.setChecked(False)
