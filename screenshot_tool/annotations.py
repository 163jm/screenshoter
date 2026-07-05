"""标注图形数据结构。

每个标注是用户在截图上绘制的一个图层,支持撤销。
所有坐标基于原始截图(全屏虚拟桌面)坐标系。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

from PyQt5.QtCore import Qt, QPoint, QRect, QPointF
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPixmap, QImage,
    QPolygonF, QPainterPath,
)


class ToolType(Enum):
    RECT = "rect"        # 矩形
    ELLIPSE = "ellipse"  # 椭圆
    ARROW = "arrow"      # 箭头
    PEN = "pen"          # 画笔(自由曲线)
    MOSAIC = "mosaic"    # 马赛克
    TEXT = "text"        # 文字
    ERASER = "eraser"    # 橡皮(撤销单个标注)


@dataclass
class Annotation:
    tool: ToolType
    color: QColor
    width: int
    # 各工具使用的字段
    points: List[QPoint] = field(default_factory=list)  # PEN/ARROW/RECT/ELLIPSE 起止
    text: str = ""
    font_size: int = 16
    # 马赛克区域(基于 points[0] 与 points[1] 矩形)

    def draw(self, painter: QPainter, mosaic_source: QPixmap = None):
        pen = QPen(self.color, self.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if self.tool == ToolType.PEN:
            if len(self.points) < 2:
                return
            path = QPainterPath()
            path.moveTo(self.points[0])
            for p in self.points[1:]:
                path.lineTo(p)
            painter.drawPath(path)

        elif self.tool == ToolType.RECT:
            if len(self.points) >= 2:
                r = QRect(self.points[0], self.points[1]).normalized()
                painter.drawRect(r)

        elif self.tool == ToolType.ELLIPSE:
            if len(self.points) >= 2:
                r = QRect(self.points[0], self.points[1]).normalized()
                painter.drawEllipse(r)

        elif self.tool == ToolType.ARROW:
            if len(self.points) >= 2:
                self._draw_arrow(painter, self.points[0], self.points[1])

        elif self.tool == ToolType.TEXT:
            if self.text:
                font = QFont("Microsoft YaHei", self.font_size, QFont.Bold)
                painter.setFont(font)
                painter.setPen(QPen(self.color))
                # 多行
                lines = self.text.split("\n")
                fm = painter.fontMetrics()
                lh = fm.height()
                x = self.points[0].x()
                y = self.points[0].y() + fm.ascent()
                for ln in lines:
                    painter.drawText(QPoint(x, y), ln)
                    y += lh

        elif self.tool == ToolType.MOSAIC:
            if mosaic_source is not None and len(self.points) >= 2:
                r = QRect(self.points[0], self.points[1]).normalized()
                # 把对应区域绘制为像素化效果
                self._draw_mosaic(painter, mosaic_source, r)

    def _draw_arrow(self, painter: QPainter, start: QPoint, end: QPoint):
        # 画主线 + 箭头
        painter.drawLine(start, end)
        # 箭头角度
        import math
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        # 箭头长度 = max(10, pen.width * 4), 张角 30°
        ah = max(10, self.width * 4)
        angle = math.atan2(dy, dx)
        a1 = angle + math.pi - math.radians(15)
        a2 = angle + math.pi + math.radians(15)
        p1 = QPointF(end.x() + ah * math.cos(a1), end.y() + ah * math.sin(a1))
        p2 = QPointF(end.x() + ah * math.cos(a2), end.y() + ah * math.sin(a2))
        poly = QPolygonF([QPointF(end), p1, p2])
        painter.setBrush(QBrush(self.color))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(poly)

    def _draw_mosaic(self, painter: QPainter, src: QPixmap, rect: QRect):
        """把 src 中 rect 区域像素化后绘制到 painter 的 rect 上。"""
        if rect.width() <= 0 or rect.height() <= 0:
            return
        block = max(4, 8)  # 像素块大小
        # 缩小再放大实现马赛克
        small = src.copy(rect).scaled(
            max(1, rect.width() // block),
            max(1, rect.height() // block),
            Qt.IgnoreAspectRatio, Qt.FastTransformation
        ).scaled(rect.width(), rect.height(),
                 Qt.IgnoreAspectRatio, Qt.FastTransformation)
        painter.drawPixmap(rect.topLeft(), small)

    def bounding_rect(self) -> QRect:
        if not self.points:
            return QRect()
        if len(self.points) == 1:
            return QRect(self.points[0], self.points[0]).normalized()
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        return QRect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


class AnnotationLayer:
    """标注图层:维护所有标注,支持撤销,支持导出合并后的 QPixmap。"""

    def __init__(self):
        self.items: List[Annotation] = []

    def add(self, ann: Annotation):
        self.items.append(ann)

    def undo(self):
        if self.items:
            self.items.pop()

    def clear(self):
        self.items.clear()

    def is_empty(self) -> bool:
        return not self.items

    def render_to(self, base: QPixmap, mosaic_source: QPixmap) -> QPixmap:
        out = QPixmap(base.size())
        out.fill(Qt.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for ann in self.items:
            ann.draw(painter, mosaic_source)
        painter.end()
        return out
