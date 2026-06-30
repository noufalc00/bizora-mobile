"""Background warm-up for the Qt WebEngine process used by A4 print preview."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer

LOGGER = logging.getLogger(__name__)

_PREWARM_STARTED = False
_PREWARM_CONTAINER = None


def schedule_a4_preview_engine_prewarm(delay_ms: int = 1200) -> None:
    """Load Chromium in the background so Print Settings opens faster later."""
    global _PREWARM_STARTED
    if _PREWARM_STARTED:
        return
    QTimer.singleShot(max(0, int(delay_ms)), _prewarm_a4_preview_engine)


def _prewarm_a4_preview_engine() -> None:
    """Create a hidden web view and render a blank page once."""
    global _PREWARM_STARTED, _PREWARM_CONTAINER
    if _PREWARM_STARTED:
        return
    _PREWARM_STARTED = True
    try:
        from PySide6.QtWidgets import QWidget
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except Exception as exc:
        LOGGER.debug("A4 preview engine prewarm skipped: %s", exc)
        return

    try:
        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        browser = QWebEngineView(container)
        browser.setHtml("<html><body style='background:#f3f4f6;'></body></html>")
        container.resize(2, 2)
        container.show()
        _PREWARM_CONTAINER = container
        LOGGER.debug("A4 preview engine prewarm started")
    except Exception as exc:
        LOGGER.debug("A4 preview engine prewarm failed: %s", exc)
