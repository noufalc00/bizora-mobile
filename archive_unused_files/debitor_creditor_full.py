"""
Debitor/Creditor widget for the Accounting Desktop Application.
Manages debtors, creditors, and parties with company-wise data storage.
"""

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor

from config import COLORS, active_company_manager
from db import Database


class DebitorCreditorWidget(QWidget):

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.current_party_id = None
        self.parties_data = []
        self.setup_ui()
        self.load_parties()
        self.clear_form()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Debitor / Creditor")
        title.setStyleSheet("font-size:24px; font-weight:bold; color:#60a5fa;")
        layout.addWidget(title)

        # Create navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 10, 0, 10)
        
        self.entry_btn = QPushButton("Party Entry")
        self.entry_btn.setStyleSheet("""
            QPushButton {
                background-color: #60a5fa;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
        """)
        self.entry_btn.clicked.connect(self.show_entry_page)
        
        self.list_btn = QPushButton("Party List")
        self.list_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.list_btn.clicked.connect(self.show_list_page)
        
        nav_layout.addWidget(self.entry_btn)
        nav_layout.addWidget(self.list_btn)
        nav_layout.addStretch()
        
        layout.addLayout(nav_layout)

        # Create stacked widget for internal pages
        self.stack_widget = QStackedWidget()
        
        # Create pages
        self.entry_page = self.create_entry_page()
        self.list_page = self.create_list_page()
        
        self.stack_widget.addWidget(self.entry_page)
        self.stack_widget.addWidget(self.list_page)
        
        layout.addWidget(self.stack_widget)

    def show_entry_page(self, clear_form=True):
        """Switch to Party Entry page."""
        self.stack_widget.setCurrentWidget(self.entry_page)
        self.entry_btn.setStyleSheet("""
            QPushButton {
                background-color: #60a5fa;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
        """)
        self.list_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        
        # Clear form when opening normally (not for editing)
        if clear_form:
            self.clear_form()

    def show_list_page(self):
        """Switch to Party List page."""
        self.stack_widget.setCurrentWidget(self.list_page)
        self.list_btn.setStyleSheet("""
            QPushButton {
                background-color: #60a5fa;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
        """)
        self.entry_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        # Refresh party list when switching to list page
        self.load_parties()

    def label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("""
            QLabel {
                color: #fbbf24;
                font-size: 16px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 8px 0px;
                margin: 0px;
                min-height: 24px;
                height: 24px;
            }
        """)
        return lbl

    def create_entry_page(self):
        # Create container for the entry page
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # Create input field styles
        input_style = """
            QLineEdit {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
                min-height: 20px;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                outline: none;
            }
        """

        text_edit_style = """
            QTextEdit {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
            }
            QTextEdit:focus {
                border-color: #60a5fa;
                outline: none;
            }
        """

        label_style = """
            QLabel {
                color: #fbbf24;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 4px 0px;
                margin: 0px;
                min-height: 20px;
            }
        """

        # Party Name
        party_name_label = QLabel("Party Name *")
        party_name_label.setStyleSheet(label_style)
        self.party_name_input = QLineEdit()
        self.party_name_input.setStyleSheet(input_style)
        layout.addWidget(party_name_label)
        layout.addWidget(self.party_name_input)
        layout.addSpacing(5)

        # Party Type
        party_type_label = QLabel("Party Type *")
        party_type_label.setStyleSheet(label_style)
        self.party_type_combo = QComboBox()
        self.party_type_combo.addItems(["Debitor", "Creditor", "Both"])
        self.party_type_combo.setStyleSheet("""
            QComboBox {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
                min-height: 20px;
            }
            QComboBox:focus {
                border-color: #60a5fa;
                outline: none;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #f3f4f6;
            }
        """)
        layout.addWidget(party_type_label)
        layout.addWidget(self.party_type_combo)
        layout.addSpacing(5)

        # Opening Balance and Mobile Number row
        balance_mobile_row = QHBoxLayout()
        balance_mobile_row.setSpacing(10)
        
        opening_balance_label = QLabel("Opening Balance")
        opening_balance_label.setStyleSheet(label_style)
        self.opening_balance_input = QLineEdit()
        self.opening_balance_input.setPlaceholderText("0.00")
        self.opening_balance_input.setStyleSheet(input_style)
        self.opening_balance_input.setMaximumWidth(200)
        
        mobile_label = QLabel("Mobile Number")
        mobile_label.setStyleSheet(label_style)
        self.mobile_input = QLineEdit()
        self.mobile_input.setPlaceholderText("Enter mobile number")
        self.mobile_input.setStyleSheet(input_style)
        
        balance_mobile_row.addWidget(opening_balance_label)
        balance_mobile_row.addWidget(self.opening_balance_input)
        balance_mobile_row.addStretch()
        balance_mobile_row.addWidget(mobile_label)
        balance_mobile_row.addWidget(self.mobile_input)
        balance_mobile_row.addStretch()
        layout.addLayout(balance_mobile_row)
        layout.addSpacing(5)

        # Email and Credit Limit row
        email_credit_row = QHBoxLayout()
        email_credit_row.setSpacing(10)
        
        email_label = QLabel("Email")
        email_label.setStyleSheet(label_style)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter email")
        self.email_input.setStyleSheet(input_style)
        
        credit_limit_label = QLabel("Credit Limit")
        credit_limit_label.setStyleSheet(label_style)
        self.credit_limit_input = QLineEdit()
        self.credit_limit_input.setPlaceholderText("0.00")
        self.credit_limit_input.setStyleSheet(input_style)
        
        email_credit_row.addWidget(email_label)
        email_credit_row.addWidget(self.email_input)
        email_credit_row.addStretch()
        email_credit_row.addWidget(credit_limit_label)
        email_credit_row.addWidget(self.credit_limit_input)
        email_credit_row.addStretch()
        layout.addLayout(email_credit_row)
        layout.addSpacing(5)

        # GSTIN
        gstin_label = QLabel("GSTIN")
        gstin_label.setStyleSheet(label_style)
        self.gstin_input = QLineEdit()
        self.gstin_input.setPlaceholderText("Enter GSTIN")
        self.gstin_input.setStyleSheet(input_style)
        layout.addWidget(gstin_label)
        layout.addWidget(self.gstin_input)
        layout.addSpacing(5)

        # Contact Person
        contact_person_label = QLabel("Contact Person")
        contact_person_label.setStyleSheet(label_style)
        self.contact_person_input = QLineEdit()
        self.contact_person_input.setPlaceholderText("Enter contact person name")
        self.contact_person_input.setStyleSheet(input_style)
        layout.addWidget(contact_person_label)
        layout.addWidget(self.contact_person_input)
        layout.addSpacing(5)

        # Address
        address_label = QLabel("Address")
        address_label.setStyleSheet(label_style)
        self.address_input = QTextEdit()
        self.address_input.setPlaceholderText("Enter address")
        self.address_input.setMaximumHeight(80)
        self.address_input.setStyleSheet(text_edit_style)
        layout.addWidget(address_label)
        layout.addWidget(self.address_input)
        layout.addSpacing(5)

        # Notes
        notes_label = QLabel("Notes")
        notes_label.setStyleSheet(label_style)
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Enter notes")
        self.notes_input.setMaximumHeight(80)
        self.notes_input.setStyleSheet(text_edit_style)
        layout.addWidget(notes_label)
        layout.addWidget(self.notes_input)
        layout.addSpacing(10)

        # Action buttons
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.save_btn.clicked.connect(self.save)
        
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #6b7280;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        clear_btn.clicked.connect(self.clear_form)
        
        actions_row.addWidget(self.save_btn)
        actions_row.addWidget(clear_btn)
        actions_row.addStretch()
        
        layout.addLayout(actions_row)
        layout.addStretch()

        return container

    def create_list_page(self):
        # Create container for the list page
        container = QFrame()
        container.setObjectName("partyListOuterFrame")
        container.setStyleSheet("""
            QFrame#partyListOuterFrame {
                background-color: #1f2937;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        list_title = QLabel("Party List")
        list_title.setStyleSheet("""
            QLabel {
                color: #fbbf24;
                font-size: 18px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        layout.addWidget(list_title)

        # Search row
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 10)

        search_label = QLabel("Search:")
        search_label.setStyleSheet("""
            QLabel {
                color: #fbbf24;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
                border: none;
                margin-right: 10px;
            }
        """)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by party name or mobile number...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                min-width: 300px;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                outline: none;
            }
        """)
        self.search_input.textChanged.connect(self.filter_parties)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        # Table container
        table_container = QFrame()
        table_container.setObjectName("partyListTableContainer")
        table_container.setStyleSheet("""
            QFrame#partyListTableContainer {
                background-color: #1f2937;
                border: 1px solid #4b5563;
                border-radius: 6px;
            }
        """)

        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "SL No",
            "Party Name",
            "Party Type",
            "Opening Balance",
            "Mobile Number",
            "Email"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.table.itemDoubleClicked.connect(self.on_table_double_click)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)

        # Make table fully flat
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setFrameShadow(QFrame.Plain)
        self.table.setLineWidth(0)
        self.table.setMidLineWidth(0)
        self.table.setContentsMargins(0, 0, 0, 0)
        self.table.setViewportMargins(0, 0, 0, 0)

        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1f2937;
                color: #f3f4f6;
                border: none;
                gridline-color: #4b5563;
                selection-background-color: #60a5fa;
                selection-color: white;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #4b5563;
            }
            QTableWidget::item:selected {
                background-color: #60a5fa;
                color: white;
            }
            QHeaderView::section {
                background-color: #374151;
                color: #fbbf24;
                font-weight: bold;
                font-size: 14px;
                border: none;
                border-right: 1px solid #4b5563;
                border-bottom: 1px solid #4b5563;
                padding-left: 8px;
                padding-right: 8px;
            }
            QTableCornerButton::section {
                background-color: #374151;
                border: none;
            }
        """)

        header = self.table.horizontalHeader()
        header.setVisible(True)
        header.setFixedHeight(36)
        header.setMinimumHeight(36)
        header.setDefaultSectionSize(36)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setMinimumSectionSize(60)

        # Set fixed column widths as specified
        self.table.setColumnWidth(0, 80)   # SL No
        self.table.setColumnWidth(1, 260)  # Party Name
        self.table.setColumnWidth(2, 140)  # Party Type
        self.table.setColumnWidth(3, 140)  # Opening Balance
        self.table.setColumnWidth(4, 150)  # Mobile Number
        self.table.setColumnWidth(5, 220)  # Email
        table_layout.addWidget(self.table)
        layout.addWidget(table_container)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)

        edit_btn = QPushButton("Edit Selected")
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #60a5fa;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
        """)
        edit_btn.clicked.connect(self.edit_selected_party)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        delete_btn.clicked.connect(self.delete_selected_party)

        button_layout.addWidget(edit_btn)
        button_layout.addWidget(delete_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        return container

    def clear_form(self):
        self.party_name_input.clear()
        self.party_type_combo.setCurrentIndex(0)
        self.opening_balance_input.clear()
        self.mobile_input.clear()
        self.email_input.clear()
        self.gstin_input.clear()
        self.credit_limit_input.clear()
        self.contact_person_input.clear()
        self.address_input.clear()
        self.notes_input.clear()
        self.current_party_id = None

    def save(self):
        # Check if company is active
        active_company = active_company_manager.get_active_company()
        if not active_company:
            QMessageBox.warning(self, "No Active Company", "Please open a company first.")
            return
        
        # Validate required fields
        party_name = self.party_name_input.text().strip()
        if not party_name:
            QMessageBox.warning(self, "Validation Error", "Party Name is required.")
            self.party_name_input.setFocus()
            return

        party_type = self.party_type_combo.currentText()
        if not party_type:
            QMessageBox.warning(self, "Validation Error", "Party Type is required.")
            self.party_type_combo.setFocus()
            return

        conn = None
        try:
            # Get field values
            opening_balance = float(self.opening_balance_input.text() or "0")
            mobile_number = self.mobile_input.text().strip()
            email = self.email_input.text().strip()
            gstin = self.gstin_input.text().strip()
            credit_limit = float(self.credit_limit_input.text() or "0")
            contact_person = self.contact_person_input.text().strip()
            address = self.address_input.toPlainText().strip()
            notes = self.notes_input.toPlainText().strip()

            conn = self.db.connect()
            cursor = conn.cursor()

            # Check for duplicate party name in same company
            if self.current_party_id:
                cursor.execute(
                    "SELECT id FROM parties WHERE name = ? AND company_id = ? AND id != ?",
                    (party_name, active_company['id'], self.current_party_id)
                )
            else:
                cursor.execute(
                    "SELECT id FROM parties WHERE name = ? AND company_id = ?",
                    (party_name, active_company['id'])
                )

            if cursor.fetchone():
                QMessageBox.warning(
                    self,
                    "Duplicate Party",
                    f"Party '{party_name}' already exists in this company."
                )
                return

            if self.current_party_id:
                # Update existing party
                cursor.execute(
                    '''
                    UPDATE parties
                    SET name = ?, party_type = ?, opening_balance = ?, mobile_number = ?,
                        email = ?, gstin = ?, credit_limit = ?, contact_person = ?,
                        address = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND company_id = ?
                    ''',
                    (
                        party_name, party_type, opening_balance, mobile_number,
                        email, gstin, credit_limit, contact_person,
                        address, notes, self.current_party_id, active_company['id']
                    )
                )
            else:
                # Insert new party
                cursor.execute(
                    '''
                    INSERT INTO parties (
                        company_id, name, party_type, opening_balance, mobile_number,
                        email, gstin, credit_limit, contact_person, address, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        active_company['id'], party_name, party_type, opening_balance, mobile_number,
                        email, gstin, credit_limit, contact_person, address, notes
                    )
                )

            conn.commit()
            QMessageBox.information(self, "Success", "Party saved successfully.")
            self.clear_form()
            # Set focus to Party Name field after clear
            QTimer.singleShot(0, lambda: self.party_name_input.setFocus())
            # Refresh party list in background
            self.load_parties()
            # Reapply current search filter if any
            search_term = self.search_input.text().strip()
            if search_term:
                self.filter_parties(search_term)

        except ValueError:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please enter valid numeric values for Opening Balance and Credit Limit."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save party: {str(e)}")
        finally:
            if conn:
                conn.close()

    def load_parties(self):
        """Load all parties from database into memory."""
        conn = None
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                self.parties_data = []
                self.render_parties([])
                return

            conn = self.db.connect()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, name, party_type, opening_balance, mobile_number,
                       email, gstin, credit_limit, contact_person, address, notes
                FROM parties
                WHERE company_id = ?
                ORDER BY name
            """, (active_company['id'],))

            self.parties_data = cursor.fetchall()
            
            # Render all parties initially
            self.render_parties(self.parties_data)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load parties: {str(e)}")
            self.parties_data = []
            self.render_parties([])
        finally:
            if conn:
                conn.close()

    def render_parties(self, parties):
        """Render parties in table."""
        self.table.setRowCount(len(parties))

        for row, party in enumerate(parties):
            sl_no_item = QTableWidgetItem(str(row + 1))
            sl_no_item.setData(Qt.UserRole, party['id'])
            self.table.setItem(row, 0, sl_no_item)

            name_item = QTableWidgetItem(party['name'])
            name_item.setData(Qt.UserRole, party['id'])
            self.table.setItem(row, 1, name_item)

            party_type_item = QTableWidgetItem(party['party_type'])
            party_type_item.setData(Qt.UserRole, party['id'])
            self.table.setItem(row, 2, party_type_item)

            opening_balance = float(party['opening_balance'] or 0)
            balance_item = QTableWidgetItem(f"{opening_balance:.2f}")
            balance_item.setData(Qt.UserRole, party['id'])
            balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, balance_item)

            mobile_item = QTableWidgetItem(party['mobile_number'] or "")
            mobile_item.setData(Qt.UserRole, party['id'])
            self.table.setItem(row, 4, mobile_item)

            email_item = QTableWidgetItem(party['email'] or "")
            email_item.setData(Qt.UserRole, party['id'])
            self.table.setItem(row, 5, email_item)

    def filter_parties(self, search_term):
        """Filter parties in memory based on search term."""
        search_term = search_term.strip()
        
        if not search_term:
            # Show all parties if search is empty
            self.render_parties(self.parties_data)
            return
        
        # Filter parties in memory
        filtered_parties = []
        for party in self.parties_data:
            # Case insensitive search in name and mobile number
            name_match = search_term.lower() in (party['name'] or "").lower()
            mobile_match = search_term.lower() in (party['mobile_number'] or "").lower()
            
            if name_match or mobile_match:
                filtered_parties.append(party)
        
        # Render filtered parties
        self.render_parties(filtered_parties)
    
    def on_table_selection_changed(self):
        """Handle table row selection change."""
        pass

    def on_table_double_click(self, item):
        """Handle double-click on table row to edit party."""
        self.edit_selected_party()

    def edit_selected_party(self):
        """Edit the selected party by switching to entry page."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a party to edit.")
            return

        # Get party ID from UserRole data of the first selected item
        party_id = selected_items[0].data(Qt.UserRole)
        if not party_id:
            QMessageBox.warning(self, "Error", "Unable to identify selected party.")
            return
        
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, party_type, opening_balance, mobile_number,
                       email, gstin, credit_limit, contact_person, address, notes
                FROM parties 
                WHERE company_id = ? AND id = ?
            """, (active_company['id'], party_id))
            
            party = cursor.fetchone()
            conn.close()
            
            if party:
                self.load_party_to_form(party)
                self.show_entry_page(clear_form=False)
            else:
                QMessageBox.warning(self, "Error", "Party not found.")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load party: {str(e)}")

    def delete_selected_party(self):
        """Delete the selected party."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a party to delete.")
            return

        # Get party ID and name from selected row
        party_id = selected_items[0].data(Qt.UserRole)
        selected_row = self.table.currentRow()
        party_name_item = self.table.item(selected_row, 1)
        party_name = party_name_item.text() if party_name_item else "selected party"
        
        if not party_id:
            QMessageBox.warning(self, "Error", "Unable to identify selected party.")
            return
        
        conn = None
        try:
            active_company = active_company_manager.get_active_company()
            if not active_company:
                return
            
            # Confirm deletion
            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete '{party_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM parties WHERE id = ? AND company_id = ?", 
                             (party_id, active_company['id']))
                conn.commit()
                
                QMessageBox.information(self, "Success", "Party deleted successfully.")
                # Refresh party list and reapply search filter
                self.load_parties()
                search_term = self.search_input.text().strip()
                if search_term:
                    self.filter_parties(search_term)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete party: {str(e)}")
        finally:
            if conn:
                conn.close()

    def load_party_to_form(self, party):
        """Load party data into form fields."""
        self.current_party_id = party['id']
        self.party_name_input.setText(party['name'])
        self.party_type_combo.setCurrentText(party['party_type'])
        self.opening_balance_input.setText(str(party['opening_balance']))
        self.mobile_input.setText(party['mobile_number'] or "")
        self.email_input.setText(party['email'] or "")
        self.gstin_input.setText(party['gstin'] or "")
        self.credit_limit_input.setText(str(party['credit_limit']))
        self.contact_person_input.setText(party['contact_person'] or "")
        self.address_input.setPlainText(party['address'] or "")
        self.notes_input.setPlainText(party['notes'] or "")

    def keyPressEvent(self, event):
        """Handle key press events for Enter and Esc navigation."""
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Get current focus widget
            focus_widget = self.focusWidget()
            
            # Define tab order for form fields
            field_order = [
                self.party_name_input,
                self.party_type_combo,
                self.opening_balance_input,
                self.mobile_input,
                self.email_input,
                self.credit_limit_input,
                self.gstin_input,
                self.contact_person_input,
                self.address_input,
                self.notes_input
            ]
            
            if focus_widget in field_order:
                # Normal field navigation
                current_index = field_order.index(focus_widget)
                if current_index < len(field_order) - 1:
                    next_field = field_order[current_index + 1]
                    self.focus_and_select(next_field)
                else:
                    # If at last field, trigger save
                    self.save()
            elif focus_widget == self.save_btn:
                # If Save button has focus, trigger save
                self.save()
        elif event.key() == Qt.Key_Escape:
            # Get current focus widget
            focus_widget = self.focusWidget()
            
            # Define tab order for form fields
            field_order = [
                self.party_name_input,
                self.party_type_combo,
                self.opening_balance_input,
                self.mobile_input,
                self.email_input,
                self.credit_limit_input,
                self.gstin_input,
                self.contact_person_input,
                self.address_input,
                self.notes_input
            ]
            
            # Find current field in order and move to previous
            if focus_widget in field_order:
                current_index = field_order.index(focus_widget)
                if current_index > 0:
                    prev_field = field_order[current_index - 1]
                    if isinstance(prev_field, QTextEdit):
                        prev_field.setFocus()
                        prev_field.moveCursor(QTextCursor.End)
                    else:
                        self.focus_and_select(prev_field)
        else:
            super().keyPressEvent(event)

    def focus_and_select(self, widget):
        """Set focus and select all text with proper timing."""
        widget.setFocus()
        QTimer.singleShot(0, widget.selectAll)
