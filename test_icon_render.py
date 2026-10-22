"""Tests icon rendering in memory with PySide6."""
from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

app = QApplication([])

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round">
{content}
</svg>"""

circle_path = '<circle cx="12" cy="12" r="10"/>'
svg_str = SVG_TEMPLATE.format(color="#2563EB", stroke_width=2, content=circle_path)

renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
pixmap = QPixmap(32, 32)
pixmap.fill(Qt.GlobalColor.transparent)
painter = QPainter(pixmap)
renderer.render(painter)
painter.end()

icon = QIcon(pixmap)
print("Icon created:", not icon.isNull(), "Pixmap created:", not pixmap.isNull())
