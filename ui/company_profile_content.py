"""
Read-only company profile content with section headings.
Shows only fields that contain data.
"""

from html import escape
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

from ui import theme
from ui.universal_preview_dialog import UniversalPreviewDialog


FIELD_SECTIONS = (
    (
        "Basic Information",
        (
            ("GSTIN", "gstin"),
            ("GST Registration Type", "gst_type"),
            ("Phone", "phone_number"),
            ("Email", "email"),
        ),
    ),
    (
        "Business Details",
        (
            ("Business Type", "business_type"),
            ("Business Category", "business_category"),
        ),
    ),
    (
        "Address Information",
        (
            ("Address", "address", True),
            ("State", "state"),
            ("Pincode", "pincode"),
        ),
    ),
)

PRINT_SETTINGS = (
    ("Phone", "print_phone"),
    ("GSTIN", "print_gstin"),
    ("Email", "print_email"),
    ("Business Type", "print_business_type"),
    ("Business Category", "print_business_category"),
    ("Address", "print_address"),
    ("State", "print_state"),
    ("Pincode", "print_pincode"),
    ("Logo", "print_logo"),
    ("Signature", "print_signature"),
)


def _has_value(value) -> bool:
    """Return True when a company field contains displayable text."""
    text = str(value or "").strip()
    return bool(text) and text.lower() not in {"select...", "n/a"}


def _profile_stylesheet() -> str:
    """Return shared styling for company profile views."""
    from ui import theme
    return theme.master_profile_stylesheet()


class CompanyProfileContentWidget(UiMemoryMixin, QWidget):
    """Scrollable company profile that lists only filled fields under headings."""

    def __init__(self, company_data=None, parent=None, show_actions: bool = False):
        super().__init__(parent)
        self.company_data = company_data or {}
        self.show_actions = show_actions
        self.logo_preview = None
        self.signature_preview = None
        self.setStyleSheet(_profile_stylesheet())

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(20)
        self.rebuild()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)

    def refresh_theme(self) -> None:
        self.setStyleSheet(_profile_stylesheet())
        if self.company_data:
            self.rebuild()

    def set_company_data(self, company_data) -> None:
        """Replace the displayed company record."""
        self.company_data = company_data or {}
        self.rebuild()

    def rebuild(self) -> None:
        """Rebuild the profile from the current company record."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.company_data:
            empty_label = QLabel("No company data available.")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(
                f"color: {theme.legacy_colors()['text_secondary']}; font-size: 15px; padding: 40px;"
            )
            self._layout.addWidget(empty_label)
            return

        self._create_header(self._layout)

        for section_title, fields in FIELD_SECTIONS:
            self._create_field_section(self._layout, section_title, fields)

        if self._has_media_data():
            self._create_media_section(self._layout)

        self._create_print_settings_section(self._layout)
        self._create_record_section(self._layout)

        if self.show_actions:
            self._create_action_buttons(self._layout)

        self._layout.addStretch()

    def _value(self, key: str) -> str:
        return str(self.company_data.get(key) or "").strip()

    def _print_value(self, key: str) -> str:
        return "Yes" if int(self.company_data.get(key, 1) or 0) else "No"

    def _has_media_data(self) -> bool:
        return _has_value(self.company_data.get("logo_path")) or _has_value(
            self.company_data.get("signature_path")
        )

    def _section_frame(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.legacy_colors()['surface']};
                border-radius: 8px;
                border: 1px solid {theme.legacy_colors()['border']};
                padding: 15px;
            }}
        """)
        return frame

    def _create_header(self, layout: QVBoxLayout) -> None:
        header_frame = self._section_frame()
        header_layout = QVBoxLayout(header_frame)

        title = QLabel(self._value("business_name") or "Company")
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.legacy_colors()['primary']};
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 5px;
            }}
        """)
        header_layout.addWidget(title)

        status = "Active" if self.company_data.get("is_active") else "Inactive"
        status_color = theme.legacy_colors()["success"] if self.company_data.get("is_active") else theme.legacy_colors()["warning"]
        status_label = QLabel(f"Status: {status}")
        status_label.setStyleSheet(f"""
            QLabel {{
                color: {status_color};
                font-weight: bold;
                font-size: 14px;
            }}
        """)
        header_layout.addWidget(status_label)
        layout.addWidget(header_frame)

    def _create_field_section(self, layout: QVBoxLayout, title: str, fields: tuple) -> None:
        rows = []
        for field in fields:
            label_text = field[0]
            key = field[1]
            multiline = len(field) > 2 and field[2]
            value = self._value(key)
            if _has_value(value):
                rows.append((label_text, value, multiline))

        if not rows:
            return

        section_label = QLabel(title)
        section_label.setProperty("class", "section")
        layout.addWidget(section_label)

        info_frame = self._section_frame()
        info_layout = QGridLayout(info_frame)
        info_layout.setSpacing(10)

        for row_index, (label_text, value, multiline) in enumerate(rows):
            self._add_value_row(info_layout, row_index, label_text, value, multiline)

        layout.addWidget(info_frame)

    def _add_value_row(
        self,
        grid_layout: QGridLayout,
        row: int,
        label_text: str,
        value,
        multiline: bool = False,
    ) -> None:
        field_label = QLabel(f"{label_text}:")
        field_label.setProperty("class", "field")
        grid_layout.addWidget(field_label, row, 0, Qt.AlignTop if multiline else Qt.AlignVCenter)

        if multiline:
            value_widget = QTextEdit()
            value_widget.setPlainText(str(value))
            value_widget.setReadOnly(True)
            value_widget.setMaximumHeight(100)
            value_widget.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {theme.legacy_colors()['background']};
                    color: {theme.legacy_colors()['text_primary']};
                    border: 1px solid {theme.legacy_colors()['border']};
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 13px;
                }}
            """)
        else:
            value_widget = QLabel(str(value))
            value_widget.setProperty("class", "value")
            value_widget.setWordWrap(True)

        grid_layout.addWidget(value_widget, row, 1)

    def _create_media_section(self, layout: QVBoxLayout) -> None:
        section_label = QLabel("Company Media")
        section_label.setProperty("class", "section")
        layout.addWidget(section_label)

        media_frame = self._section_frame()
        media_layout = QHBoxLayout(media_frame)
        media_layout.setSpacing(20)

        if _has_value(self.company_data.get("logo_path")):
            media_layout.addWidget(self._create_preview_section("Logo", 180, 120, "logo"))

        if _has_value(self.company_data.get("signature_path")):
            media_layout.addWidget(
                self._create_preview_section("Signature", 180, 120, "signature")
            )

        layout.addWidget(media_frame)
        self._load_media_previews()

    def _create_preview_section(self, title: str, width: int, height: int, media_key: str) -> QFrame:
        section = QFrame()
        section.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.legacy_colors()['background']};
                border: 1px solid {theme.legacy_colors()['border']};
                border-radius: 6px;
                padding: 10px;
            }}
        """)

        section_layout = QVBoxLayout(section)
        section_layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {theme.legacy_colors()['text_secondary']};
                font-weight: bold;
                font-size: 12px;
            }}
        """)
        section_layout.addWidget(title_label, alignment=Qt.AlignCenter)

        preview = QLabel()
        preview.setFixedSize(width, height)
        preview.setStyleSheet(f"""
            QLabel {{
                background-color: {theme.legacy_colors()['surface']};
                border: 1px solid {theme.legacy_colors()['border']};
                border-radius: 4px;
                color: {theme.legacy_colors()['text_secondary']};
                font-size: 11px;
            }}
        """)
        preview.setAlignment(Qt.AlignCenter)

        if media_key == "logo":
            self.logo_preview = preview
        else:
            self.signature_preview = preview

        section_layout.addWidget(preview, alignment=Qt.AlignCenter)
        return section

    def _load_media_previews(self) -> None:
        self._load_single_preview(
            self.logo_preview,
            self.company_data.get("logo_path", ""),
            "Logo",
        )
        self._load_single_preview(
            self.signature_preview,
            self.company_data.get("signature_path", ""),
            "Signature",
        )

    def _load_single_preview(self, preview: QLabel | None, file_path: str, label: str) -> None:
        if preview is None:
            return

        if not _has_value(file_path) or not os.path.exists(file_path):
            preview.setText(f"No {label} Available")
            return

        if file_path.lower().endswith(".pdf"):
            preview.setText(f"PDF Uploaded\n({label})")
            preview.setStyleSheet(f"""
                QLabel {{
                    background-color: {theme.legacy_colors()['surface']};
                    border: 1px solid {theme.legacy_colors()['border']};
                    border-radius: 4px;
                    color: {theme.legacy_colors()['primary']};
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
            return

        try:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                preview.setText(f"No {label} Available")
                return

            preview_size = preview.size()
            scaled_pixmap = pixmap.scaled(
                preview_size.width() - 10,
                preview_size.height() - 10,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            preview.setPixmap(scaled_pixmap)
            preview.setText("")
        except Exception as error:
            print(f"Error loading {label.lower()}: {error}")
            preview.setText(f"No {label} Available")

    def _create_print_settings_section(self, layout: QVBoxLayout) -> None:
        section_label = QLabel("Print on Bill Settings")
        section_label.setProperty("class", "section")
        layout.addWidget(section_label)

        info_frame = self._section_frame()
        info_layout = QGridLayout(info_frame)
        info_layout.setSpacing(10)

        for row_index, (label_text, key) in enumerate(PRINT_SETTINGS):
            self._add_value_row(info_layout, row_index, label_text, self._print_value(key))

        layout.addWidget(info_frame)

    def _create_record_section(self, layout: QVBoxLayout) -> None:
        rows = []
        if _has_value(self.company_data.get("created_at")):
            rows.append(("Created At", self._value("created_at"), False))
        if _has_value(self.company_data.get("updated_at")):
            rows.append(("Updated At", self._value("updated_at"), False))

        if not rows:
            return

        section_label = QLabel("Record Details")
        section_label.setProperty("class", "section")
        layout.addWidget(section_label)

        info_frame = self._section_frame()
        info_layout = QGridLayout(info_frame)
        info_layout.setSpacing(10)

        for row_index, (label_text, value, multiline) in enumerate(rows):
            self._add_value_row(info_layout, row_index, label_text, value, multiline)

        layout.addWidget(info_frame)

    def _create_action_buttons(self, layout: QVBoxLayout) -> None:
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        export_button = QPushButton("Export PDF")
        export_button.clicked.connect(self.export_to_pdf)
        button_layout.addWidget(export_button)

        layout.addLayout(button_layout)

    def export_to_pdf(self) -> None:
        """Open the company profile in the PDF preview/export dialog."""
        dialog = UniversalPreviewDialog(
            self._company_profile_html(),
            self,
            title=f"Company Profile - {self._value('business_name') or 'Company'}",
        )
        dialog.exec()

    def _company_profile_html(self) -> str:
        """Return printable HTML for the filled company profile."""
        sections = []

        basic_rows = [
            ("Business Name", self._value("business_name")),
            ("Phone Number", self._value("phone_number")),
            ("GSTIN", self._value("gstin")),
            ("GST Registration Type", self._value("gst_type")),
            ("Email", self._value("email")),
        ]
        basic_rows = [(label, value) for label, value in basic_rows if _has_value(value)]
        if basic_rows:
            sections.append(("Company Information", basic_rows))

        business_rows = [
            ("Business Type", self._value("business_type")),
            ("Business Category", self._value("business_category")),
            ("Address", self._value("address")),
            ("State", self._value("state")),
            ("Pincode", self._value("pincode")),
        ]
        business_rows = [(label, value) for label, value in business_rows if _has_value(value)]
        if business_rows:
            sections.append(("Business Details", business_rows))

        upload_rows = []
        if _has_value(self.company_data.get("logo_path")):
            upload_rows.append(("Logo Path", self._value("logo_path")))
        if _has_value(self.company_data.get("signature_path")):
            upload_rows.append(("Signature Path", self._value("signature_path")))
        if upload_rows:
            sections.append(("Upload Details", upload_rows))

        record_rows = [
            ("Status", "Active" if self.company_data.get("is_active") else "Inactive"),
        ]
        if _has_value(self.company_data.get("created_at")):
            record_rows.append(("Created At", self._value("created_at")))
        if _has_value(self.company_data.get("updated_at")):
            record_rows.append(("Updated At", self._value("updated_at")))
        sections.append(("Record Details", record_rows))

        section_html = []
        for title, rows in sections:
            row_html = "".join(
                f"<tr><th>{escape(label)}</th><td>{escape(str(value))}</td></tr>"
                for label, value in rows
            )
            section_html.append(f"<h2>{escape(title)}</h2><table>{row_html}</table>")

        business_name = escape(self._value("business_name") or "Company")
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    color: #111827;
                    margin: 24px;
                }}
                h1 {{
                    color: #1d4ed8;
                    border-bottom: 2px solid #1d4ed8;
                    padding-bottom: 8px;
                }}
                h2 {{
                    color: #1f2937;
                    margin-top: 22px;
                    border-bottom: 1px solid #d1d5db;
                    padding-bottom: 4px;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin-top: 8px;
                }}
                th, td {{
                    border: 1px solid #d1d5db;
                    padding: 8px;
                    text-align: left;
                    vertical-align: top;
                }}
                th {{
                    width: 32%;
                    background-color: #eff6ff;
                    color: #1f2937;
                }}
            </style>
        </head>
        <body>
            <h1>Company Profile - {business_name}</h1>
            {''.join(section_html)}
        </body>
        </html>
        """