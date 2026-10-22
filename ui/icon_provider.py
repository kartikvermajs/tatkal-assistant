"""Local SVG icon provider for Tatkal Assistant desktop application.

Provides clean, crisp, local vector icons rendered at any target size and color
without requiring internet access or external fonts/emojis.
"""

import os
from typing import Dict, Optional
from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round">
{content}
</svg>"""

ICON_PATHS: Dict[str, str] = {
    "train": """<rect x="4" y="3" width="16" height="16" rx="2"/>
<path d="M4 11h16"/>
<path d="M12 3v8"/>
<path d="m8 19-2 3"/>
<path d="m16 19 2 3"/>
<circle cx="8" cy="15" r="1" fill="{color}"/>
<circle cx="16" cy="15" r="1" fill="{color}"/>""",

    "users": """<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
<circle cx="9" cy="7" r="4"/>
<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
<path d="M16 3.13a4 4 0 0 1 0 7.75"/>""",

    "user": """<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
<circle cx="12" cy="7" r="4"/>""",

    "user-check": """<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
<circle cx="9" cy="7" r="4"/>
<polyline points="16 11 18 13 22 9"/>""",

    "globe": """<circle cx="12" cy="12" r="10"/>
<line x1="2" y1="12" x2="22" y2="12"/>
<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>""",

    "clock": """<circle cx="12" cy="12" r="10"/>
<polyline points="12 6 12 12 16 14"/>""",

    "shield": """<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
<circle cx="12" cy="11" r="2" fill="{color}"/>""",

    "credit-card": """<rect x="2" y="5" width="20" height="14" rx="2"/>
<line x1="2" y1="10" x2="22" y2="10"/>""",

    "check": """<polyline points="20 6 9 17 4 12"/>""",

    "check-circle": """<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
<polyline points="22 4 12 14.01 9 11.01"/>""",

    "alert-triangle": """<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
<line x1="12" y1="9" x2="12" y2="13"/>
<line x1="12" y1="17" x2="12.01" y2="17"/>""",

    "x-circle": """<circle cx="12" cy="12" r="10"/>
<line x1="15" y1="9" x2="9" y2="15"/>
<line x1="9" y1="9" x2="15" y2="15"/>""",

    "play": """<polygon points="6 3 20 12 6 21 6 3" fill="{color}"/>""",

    "stop": """<rect x="5" y="5" width="14" height="14" rx="2" fill="{color}"/>""",

    "x": """<line x1="18" y1="6" x2="6" y2="18"/>
<line x1="6" y1="6" x2="18" y2="18"/>""",

    "save": """<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
<polyline points="17 21 17 13 7 13 7 21"/>
<polyline points="7 3 7 8 15 8"/>""",

    "list": """<line x1="8" y1="6" x2="21" y2="6"/>
<line x1="8" y1="12" x2="21" y2="12"/>
<line x1="8" y1="18" x2="21" y2="18"/>
<line x1="3" y1="6" x2="3.01" y2="6"/>
<line x1="3" y1="12" x2="3.01" y2="12"/>
<line x1="3" y1="18" x2="3.01" y2="18"/>""",

    "history": """<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
<path d="M3 3v5h5"/>
<polyline points="12 7 12 12 15 15"/>""",

    "file-text": """<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
<polyline points="14 2 14 8 20 8"/>
<line x1="16" y1="13" x2="8" y2="13"/>
<line x1="16" y1="17" x2="8" y2="17"/>""",

    "arrow-right": """<line x1="5" y1="12" x2="19" y2="12"/>
<polyline points="12 5 19 12 12 19"/>""",

    "circle-dot": """<circle cx="12" cy="12" r="10"/>
<circle cx="12" cy="12" r="4" fill="{color}"/>""",

    "circle": """<circle cx="12" cy="12" r="9"/>""",
}

_PIXMAP_CACHE: Dict[str, QPixmap] = {}
_ICON_CACHE: Dict[str, QIcon] = {}


def get_svg_string(name: str, color: str = "#1E293B", stroke_width: float = 2.0) -> str:
    """Return complete SVG XML string with injected color."""
    raw_content = ICON_PATHS.get(name, ICON_PATHS["circle"])
    content = raw_content.replace("{color}", color)
    return SVG_TEMPLATE.format(color=color, stroke_width=stroke_width, content=content)


def get_pixmap(name: str, color: str = "#1E293B", size: int = 18, stroke_width: float = 2.0) -> QPixmap:
    """Render a named SVG icon to a transparent QPixmap."""
    cache_key = f"{name}_{color}_{size}_{stroke_width}"
    if cache_key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[cache_key]

    svg_str = get_svg_string(name, color=color, stroke_width=stroke_width)
    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()

    _PIXMAP_CACHE[cache_key] = pixmap
    return pixmap


def get_icon(name: str, color: Optional[str] = None, size: int = 18, stroke_width: float = 2.0) -> QIcon:
    """Return a QIcon for a named icon."""
    default_color = color or "#1E293B"
    cache_key = f"{name}_{default_color}_{size}_{stroke_width}"
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    pixmap = get_pixmap(name, color=default_color, size=size, stroke_width=stroke_width)
    icon = QIcon(pixmap)
    _ICON_CACHE[cache_key] = icon
    return icon


def ensure_asset_icons_on_disk(base_dir: Optional[str] = None) -> None:
    """Export standard SVGs to assets/icons on disk for PyInstaller bundling."""
    target_dir = os.path.join(base_dir or os.getcwd(), "assets", "icons")
    try:
        os.makedirs(target_dir, exist_ok=True)
        for name, _ in ICON_PATHS.items():
            file_path = os.path.join(target_dir, f"{name}.svg")
            if not os.path.exists(file_path):
                svg_str = get_svg_string(name, color="#1E293B")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(svg_str)
    except Exception:
        pass


# Ensure local disk assets exist
ensure_asset_icons_on_disk()
