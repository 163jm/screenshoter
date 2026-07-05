"""截图主窗口:全屏遮罩 + 选区 + 放大镜 + 标注。

工作流程:
  1. 启动时 grabWindow 截取整个虚拟桌面 (跨多屏)
  2. 显示全屏无边框窗口,绘制半透明遮罩
  3. 鼠标按下拖动选区
  4. 选区完成后,显示工具栏,可进行标注
  5. 确认/保存/取消
"""
import sys
import datetime
import os

from PyQt5.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal, QTimer
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QFont, QImage,
    QGuiApplication, QCursor, QPainterPath, QPolygonF, QPointF,
)
from PyQt5.QtWidgets import (
    QWidget, QApplication, QFileDialog, QMessageBox, QLabel, QLineEdit,
    QDialog, QVBoxLayout, QDialogButtonBox,
)

from .annotations import Annotation, AnnotationLayer, ToolType
from .toolbar import Toolbar
from .config import Config


class Magnifier(QWidget):
    """跟随鼠标的放大镜,显示像素与坐标。独立顶级窗口。"""
    def __init__(self, source: QPixmap, size: int, zoom: int):
        super().__init__(None)
        self.source = source
        self.size = size
        self.zoom = zoom
        self.setFixedSize(size, size)
        # 独立顶级窗口,跨父窗口边界显示
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.cursor_pos = QPoint(0, 0)

    def update_cursor(self, pos: QPoint):
        self.cursor_pos = pos
        # 放大镜显示在鼠标右下方,避免遮挡
        offset = 18
        new_x = pos.x() + offset
        new_y = pos.y() + offset
        # 边界检测,防止超出屏幕
        if new_x + self.size > self.source.width():
            new_x = pos.x() - offset - self.size
        if new_y + self.size > self.source.height():
            new_y = pos.y() - offset - self.size
        self.move(new_x, new_y)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)

        # 背景框
        p.setPen(QPen(QColor("#1E1E1E"), 1))
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # 截取源图中心区域并放大
        cx = self.cursor_pos.x()
        cy = self.cursor_pos.y()
        src_size = self.size // self.zoom
        src_rect = QRect(cx - src_size // 2, cy - src_size // 2,
                         src_size, src_size)
        src_rect = src_rect.intersected(self.source.rect())
        if not src_rect.isNull() and src_rect.width() > 0:
            p.drawPixmap(self._dst_rect(src_rect), self.source, src_rect)

        # 十字准星
        mid = self.width() // 2
        p.setPen(QPen(QColor("#FF4040"), 1))
        p.drawLine(mid, 0, mid, self.height())
        p.drawLine(0, mid, self.width(), mid)

        # 中心像素 RGB 显示
        if 0 <= cx < self.source.width() and 0 <= cy < self.source.height():
            img = self.source.toImage()
            if img.valid(cx, cy):
                rgb = img.pixel(cx, cy)
                color = QColor(rgb)
                hexstr = color.name().upper()
                info = f"{hexstr}  ({cx},{cy})"
                p.fillRect(0, self.height() - 18, self.width(), 18, QColor(0, 0, 0, 180))
                p.setPen(QColor("#FFFFFF"))
                f = QFont("Consolas", 8)
                p.setFont(f)
                p.drawText(QRect(2, self.height() - 17, self.width() - 4, 16),
                           Qt.AlignCenter, info)

    def _dst_rect(self, src_rect: QRect) -> QRect:
        # 保持中心对齐
        mid = self.width() // 2
        dw = src_rect.width() * self.zoom
        dh = src_rect.height() * self.zoom
        return QRect(mid - dw // 2, mid - dh // 2, dw, dh)


class TextEditDialog(QDialog):
    """文字工具的输入对话框。"""
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("输入文字")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(320, 120)
        v = QVBoxLayout(self)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("输入文字,Enter 确认,Esc 取消")
        self.edit.setStyleSheet("font-size:14px;padding:6px;")
        v.addWidget(self.edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("确认")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)
        self.color = color

    def text(self) -> str:
        return self.edit.text()


class CaptureWindow(QWidget):
    """截图全屏窗口。"""
    finished = pyqtSignal(QPixmap)   # 用户确认 -> 给出标注后的 QPixmap
    canceled = pyqtSignal()

    STATE_IDLE = "idle"          # 等待选区
    STATE_SELECTING = "selecting" # 正在拖拽选区
    STATE_SELECTED = "selected"   # 选区完成,可标注
    STATE_DRAWING = "drawing"     # 正在绘制标注

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        # 全屏无边框、置顶、覆盖所有屏幕
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setCursor(Qt.CrossCursor)

        # 截取整个虚拟桌面
        self.full_pixmap = self._grab_full_desktop()
        self.setGeometry(self._virtual_geometry())

        self.state = self.STATE_IDLE
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.selection_rect = QRect()

        # 标注
        self.layer = AnnotationLayer()
        self.current_tool: ToolType = ToolType.RECT
        self.current_color = QColor(config.default_pen_color)
        self.current_width = config.default_pen_width
        self.drawing_annotation: Annotation = None

        # 放大镜 (独立顶级窗口)
        self.magnifier = Magnifier(
            self.full_pixmap,
            config.magnifier_size,
            config.magnifier_zoom,
        )
        self.magnifier.hide()

        # 工具栏
        self.toolbar = Toolbar(self)
        self.toolbar.hide()
        self.toolbar.TOOL_CHANGED.connect(self._on_tool_changed)
        self.toolbar.TOOL_PEN_COLOR_CHANGED.connect(self._on_color_changed)
        self.toolbar.TOOL_PEN_WIDTH_CHANGED.connect(self._on_width_changed)
        self.toolbar.UNDO_REQUESTED.connect(self._on_undo)
        self.toolbar.SAVE_REQUESTED.connect(self._on_save)
        self.toolbar.CONFIRM_REQUESTED.connect(self._on_confirm)
        self.toolbar.CANCEL_REQUESTED.connect(self._on_cancel)

        # 文字工具
        self._text_pending_pos: QPoint = None

    # ---------- 屏幕捕获 ----------
    def _grab_full_desktop(self) -> QPixmap:
        # 虚拟桌面 = 所有屏幕合并
        virt = QApplication.primaryScreen().virtualGeometry()
        # grabWindow(0) 抓取整个桌面
        return QApplication.primaryScreen().grabWindow(0, virt.x(), virt.y(),
                                                         virt.width(), virt.height())

    def _virtual_geometry(self) -> QRect:
        return QApplication.primaryScreen().virtualGeometry()

    # ---------- 事件 ----------
    def showEvent(self, event):
        super().showEvent(event)
        self.setMouseTracking(True)
        self.activateWindow()
        self.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.state == self.STATE_IDLE:
                self.state = self.STATE_SELECTING
                self.start_pos = event.globalPos() - self.frameGeometry().topLeft()
                self.end_pos = self.start_pos
                self.update()
            elif self.state == self.STATE_SELECTED:
                if self.current_tool == ToolType.TEXT:
                    # 文字:在点击位置弹出输入框
                    self._text_pending_pos = event.pos()
                    self._open_text_input()
                else:
                    self.state = self.STATE_DRAWING
                    pt = event.pos()
                    self.drawing_annotation = Annotation(
                        tool=self.current_tool,
                        color=QColor(self.current_color),
                        width=self.current_width,
                        points=[pt, pt],
                    )
        elif event.button() == Qt.RightButton:
            if self.state in (self.STATE_SELECTED, self.STATE_DRAWING):
                # 右键 = 取消当前/取消
                self._on_cancel()
            else:
                self._on_cancel()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        # 始终更新放大镜(IDLE/SELECTING/DRAWING 都显示)
        self.magnifier.update_cursor(pos)
        if self.state == self.STATE_SELECTING:
            self.end_pos = pos
            self.update()
        elif self.state == self.STATE_DRAWING and self.drawing_annotation:
            if self.current_tool == ToolType.PEN:
                self.drawing_annotation.points.append(pos)
            else:
                self._set_end_point(self.drawing_annotation, pos)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.state == self.STATE_SELECTING:
            self.end_pos = event.pos()
            self.selection_rect = QRect(self.start_pos, self.end_pos).normalized()
            if self.selection_rect.width() < 4 or self.selection_rect.height() < 4:
                # 选区太小,忽略
                self.selection_rect = QRect()
                self.state = self.STATE_IDLE
            else:
                self.state = self.STATE_SELECTED
                self._show_toolbar()
            self.update()
        elif self.state == self.STATE_DRAWING and self.drawing_annotation:
            # 完成当前标注
            self.layer.add(self.drawing_annotation)
            self.drawing_annotation = None
            self.state = self.STATE_SELECTED
            self._show_toolbar()
            self.update()

    def _set_end_point(self, ann: Annotation, pt: QPoint):
        if ann.points:
            ann.points[-1] = pt
        else:
            ann.points.append(pt)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_Escape:
            self._on_cancel()
            return
        if mods & Qt.ControlModifier and key == Qt.Key_Z:
            self._on_undo()
            return
        if mods & Qt.ControlModifier and key == Qt.Key_S:
            self._on_save()
            return
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            self._on_confirm()
            return
        # 工具快捷键
        if self.state == self.STATE_SELECTED:
            m = {
                Qt.Key_R: ToolType.RECT,
                Qt.Key_O: ToolType.ELLIPSE,
                Qt.Key_A: ToolType.ARROW,
                Qt.Key_P: ToolType.PEN,
                Qt.Key_M: ToolType.MOSAIC,
                Qt.Key_T: ToolType.TEXT,
            }
            if key in m:
                self._on_tool_changed(m[key])

    # ---------- 工具栏回调 ----------
    def _on_tool_changed(self, tool):
        self.current_tool = tool
        self.toolbar.clear_tool_selection()
        if tool in self.toolbar.tool_buttons:
            self.toolbar.tool_buttons[tool].setChecked(True)

    def _on_color_changed(self, color: QColor):
        self.current_color = color

    def _on_width_changed(self, w: int):
        self.current_width = w

    def _on_undo(self):
        self.layer.undo()
        self.update()

    def _on_save(self):
        if self.selection_rect.isNull():
            return
        pix = self._compose_result()
        default_name = "screenshot_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".png"
        save_dir = self.config.save_dir or os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存截图", os.path.join(save_dir, default_name),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg)"
        )
        if path:
            pix.save(path)
            # 同时复制到剪贴板
            cb = QGuiApplication.clipboard()
            cb.setPixmap(pix)
            QMessageBox.information(self, "已保存", f"图片已保存到:\n{path}\n同时已复制到剪贴板。")

    def _on_confirm(self):
        if self.selection_rect.isNull():
            self._on_cancel()
            return
        pix = self._compose_result()
        cb = QGuiApplication.clipboard()
        cb.setPixmap(pix)
        self.finished.emit(pix)
        self.close()

    def _on_cancel(self):
        self.canceled.emit()
        self.close()

    # ---------- 文字输入 ----------
    def _open_text_input(self):
        dlg = TextEditDialog(self.current_color, self)
        if dlg.exec_() == QDialog.Accepted and dlg.text().strip():
            ann = Annotation(
                tool=ToolType.TEXT,
                color=QColor(self.current_color),
                width=2,
                points=[self._text_pending_pos],
                text=dlg.text(),
                font_size=18,
            )
            self.layer.add(ann)
            self.update()
        self._text_pending_pos = None

    # ---------- 工具栏定位 ----------
    def _show_toolbar(self):
        if self.selection_rect.isNull():
            return
        # 默认放在选区右下方
        tb_w = self.toolbar.width()
        tb_h = self.toolbar.height()
        margin = 8
        x = self.selection_rect.right() + margin
        y = self.selection_rect.bottom() + margin
        # 超出屏幕则换到左/上
        if x + tb_w > self.width():
            x = self.selection_rect.right() - tb_w
        if y + tb_h > self.height():
            y = self.selection_rect.top() - tb_h - margin
        if x < 0:
            x = margin
        if y < 0:
            y = self.selection_rect.bottom() + margin
        self.toolbar.move(x, y)
        self.toolbar.show()
        self.toolbar.raise_()

    # ---------- 合成结果 ----------
    def _compose_result(self) -> QPixmap:
        """返回选区内的最终图片(原始截图 + 标注)。"""
        if self.selection_rect.isNull():
            return QPixmap()
        # 先把标注渲染到与全图等大的透明图层
        ann_layer = self.layer.render_to(self.full_pixmap, self.full_pixmap)
        # 合成到选区大小的输出图
        result = QPixmap(self.selection_rect.size())
        result.fill(Qt.transparent)
        p = QPainter(result)
        # 1. 原始截图选区
        p.drawPixmap(0, 0, self.full_pixmap, self.selection_rect.x(),
                     self.selection_rect.y(),
                     self.selection_rect.width(),
                     self.selection_rect.height())
        # 2. 标注层选区
        p.drawPixmap(0, 0, ann_layer, self.selection_rect.x(),
                     self.selection_rect.y(),
                     self.selection_rect.width(),
                     self.selection_rect.height())
        p.end()
        return result

    # ---------- 绘制 ----------
    def paintEvent(self, _):
        p = QPainter(self)
        # 1. 底图
        p.drawPixmap(0, 0, self.full_pixmap)

        # 2. 半透明遮罩(选区外)
        dim_color = QColor(0, 0, 0, self.config.selection_dim_color_alpha)
        p.fillRect(self.rect(), dim_color)

        # 3. 选区
        r = self._current_selection_rect()
        if not r.isNull() and r.width() > 0:
            # 选区内透明显示原始截图
            p.setClipRegion(self._region_except(r))
            p.fillRect(self.rect(), dim_color)
            p.setClipping(False)

            # 选区边框
            border = QColor(self.config.selection_border_color)
            pen = QPen(border, 2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)

            # 八方向尺寸标注
            self._draw_size_label(p, r)

            # 绘制已完成的标注(在选区内)
            for ann in self.layer.items:
                ann.draw(p, self.full_pixmap)
            # 绘制正在画的标注
            if self.drawing_annotation:
                self.drawing_annotation.draw(p, self.full_pixmap)

        # 4. 提示文字(IDLE 状态)
        if self.state == self.STATE_IDLE:
            p.setPen(QColor("#FFFFFF"))
            f = QFont("Microsoft YaHei", 11)
            p.setFont(f)
            text = "拖动鼠标选择截图区域  |  ESC 取消"
            p.drawText(self.rect(), Qt.AlignCenter, text)

        # 5. 工具栏背景(已在子控件)

    def _current_selection_rect(self) -> QRect:
        if self.state == self.STATE_SELECTING:
            return QRect(self.start_pos, self.end_pos).normalized()
        elif self.state in (self.STATE_SELECTED, self.STATE_DRAWING):
            return self.selection_rect
        return QRect()

    def _region_except(self, r: QRect):
        from PyQt5.QtGui import QRegion
        # 整个 widget 区域减去选区
        full = QRegion(self.rect())
        return full.subtracted(QRegion(r))

    def _draw_size_label(self, p: QPainter, r: QRect):
        # 选区尺寸标签
        text = f"{r.width()} × {r.height()}"
        f = QFont("Microsoft YaHei", 9)
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 12
        h = fm.height() + 4
        x = r.left()
        y = r.top() - h - 2 if r.top() - h - 2 > 0 else r.bottom() + 2
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 180)))
        p.drawRoundedRect(x, y, w, h, 3, 3)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRect(x, y, w, h), Qt.AlignCenter, text)

    # ---------- 显示/隐藏 ----------
    def start_capture(self):
        self.showFullScreen()
        self.show()
        self.raise_()
        self.activateWindow()
        self.magnifier.show()
        self.magnifier.raise_()

    def closeEvent(self, event):
        self.magnifier.hide()
        self.toolbar.hide()
        super().closeEvent(event)
