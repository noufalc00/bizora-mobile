"""
Theme-aware QMessageBox helpers for Faizan Pro Accounting.

All message prompts should route through this module so light/dark theme
tokens are applied consistently, including on the company gateway login screen.
"""

from __future__ import annotations

from typing import Optional, Union

from PySide6.QtWidgets import QMessageBox, QWidget

from ui import theme

ParentType = Optional[QWidget]
IconType = Union[QMessageBox.Icon, int]
ButtonType = QMessageBox.StandardButton


def apply_message_box_theme(message_box: QMessageBox, icon: IconType) -> None:
    """Apply the correct QMessageBox stylesheet for the active theme."""
    try:
        message_box.setStyleSheet(theme.message_box_style_for_icon(icon))
    except Exception:
        message_box.setStyleSheet(theme.message_box_style())


def show_message(
    parent: ParentType,
    icon: IconType,
    title: str,
    text: str,
    buttons: ButtonType = QMessageBox.StandardButton.Ok,
    default_button: ButtonType = QMessageBox.StandardButton.NoButton,
    informative_text: str = "",
) -> int:
    """Display a themed QMessageBox and return the pressed standard button."""
    message_box = QMessageBox(parent)
    message_box.setIcon(icon)
    message_box.setWindowTitle(title)
    message_box.setText(text)
    if informative_text:
        message_box.setInformativeText(informative_text)
    message_box.setStandardButtons(buttons)
    if default_button != QMessageBox.StandardButton.NoButton:
        message_box.setDefaultButton(default_button)
    apply_message_box_theme(message_box, icon)
    return message_box.exec()


def warning(
    parent: ParentType,
    title: str,
    text: str,
    buttons: ButtonType = QMessageBox.StandardButton.Ok,
    default_button: ButtonType = QMessageBox.StandardButton.NoButton,
) -> int:
    """Theme-aware replacement for QMessageBox.warning."""
    return show_message(
        parent,
        QMessageBox.Icon.Warning,
        title,
        text,
        buttons,
        default_button,
    )


def information(
    parent: ParentType,
    title: str,
    text: str,
    buttons: ButtonType = QMessageBox.StandardButton.Ok,
    default_button: ButtonType = QMessageBox.StandardButton.NoButton,
) -> int:
    """Theme-aware replacement for QMessageBox.information."""
    return show_message(
        parent,
        QMessageBox.Icon.Information,
        title,
        text,
        buttons,
        default_button,
    )


def critical(
    parent: ParentType,
    title: str,
    text: str,
    buttons: ButtonType = QMessageBox.StandardButton.Ok,
    default_button: ButtonType = QMessageBox.StandardButton.NoButton,
) -> int:
    """Theme-aware replacement for QMessageBox.critical."""
    return show_message(
        parent,
        QMessageBox.Icon.Critical,
        title,
        text,
        buttons,
        default_button,
    )


def question(
    parent: ParentType,
    title: str,
    text: str,
    buttons: ButtonType = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    default_button: ButtonType = QMessageBox.StandardButton.No,
) -> int:
    """Theme-aware replacement for QMessageBox.question."""
    return show_message(
        parent,
        QMessageBox.Icon.Question,
        title,
        text,
        buttons,
        default_button,
    )


def install_static_method_patch() -> None:
    """Patch QMessageBox static helpers to always apply the active theme."""
    if getattr(QMessageBox, "_faizan_theme_patch_installed", False):
        return

    @staticmethod
    def _patched_warning(
        parent: ParentType,
        title: str,
        text: str,
        buttons: ButtonType = QMessageBox.StandardButton.Ok,
        default_button: ButtonType = QMessageBox.StandardButton.NoButton,
    ) -> int:
        return warning(parent, title, text, buttons, default_button)

    @staticmethod
    def _patched_information(
        parent: ParentType,
        title: str,
        text: str,
        buttons: ButtonType = QMessageBox.StandardButton.Ok,
        default_button: ButtonType = QMessageBox.StandardButton.NoButton,
    ) -> int:
        return information(parent, title, text, buttons, default_button)

    @staticmethod
    def _patched_critical(
        parent: ParentType,
        title: str,
        text: str,
        buttons: ButtonType = QMessageBox.StandardButton.Ok,
        default_button: ButtonType = QMessageBox.StandardButton.NoButton,
    ) -> int:
        return critical(parent, title, text, buttons, default_button)

    @staticmethod
    def _patched_question(
        parent: ParentType,
        title: str,
        text: str,
        buttons: ButtonType = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default_button: ButtonType = QMessageBox.StandardButton.No,
    ) -> int:
        return question(parent, title, text, buttons, default_button)

    QMessageBox.warning = _patched_warning  # type: ignore[assignment]
    QMessageBox.information = _patched_information  # type: ignore[assignment]
    QMessageBox.critical = _patched_critical  # type: ignore[assignment]
    QMessageBox.question = _patched_question  # type: ignore[assignment]
    QMessageBox._faizan_theme_patch_installed = True  # type: ignore[attr-defined]