"""Customer form: listing, add, edit, search, and balance tracking."""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpacerItem,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain.customers.service import CustomerError, CustomerInput, CustomerService
from app.infrastructure.database.models import Customer
from app.ui.busy import saving_indicator


def _make_label(text: str) -> QLabel:
    """Create a styled form field label."""
    label = QLabel(text)
    label.setObjectName("formLabel")
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
    return label


def _make_section_title(text: str) -> QLabel:
    """Create a styled section title label."""
    label = QLabel(text)
    label.setObjectName("formSectionTitle")
    return label


def _make_separator() -> QFrame:
    """Create a thin horizontal separator line."""
    line = QFrame()
    line.setObjectName("formSeparator")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


class CustomerForm(QWidget):
    _COLUMNS = (
        "ID",
        "Name",
        "Phone",
        "Email",
        "City",
        "Address",
        "Balance",
        "Credit Limit",
        "Discount (%)",
        "Status",
    )

    def __init__(self, service: CustomerService) -> None:
        super().__init__()
        self._service = service
        self._customer_id: int | None = None
        self._opening_customer: bool = False

        # ── Page Header ──
        title = QLabel("Customers")
        title.setObjectName("pageTitle")

        subtitle = QLabel("Manage customer directory, contact details, balance, and credit limits")
        subtitle.setObjectName("formLabel")

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        # Summary Metrics Panel
        self.stat_total_label = QLabel("Total: 0")
        self.stat_total_label.setObjectName("formLabel")
        self.stat_active_label = QLabel("Active: 0")
        self.stat_active_label.setObjectName("formLabel")
        self.stat_balance_label = QLabel("Total Balance: $0.00")
        self.stat_balance_label.setObjectName("formLabel")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        stats_row.addWidget(self.stat_total_label)
        stats_row.addWidget(self.stat_active_label)
        stats_row.addWidget(self.stat_balance_label)
        stats_row.addStretch(1)

        title_and_stats = QHBoxLayout()
        title_and_stats.addLayout(title_block, stretch=1)
        title_and_stats.addLayout(stats_row)

        # ── Tab Widget ──
        self._tabs = QTabWidget()
        self._tabs.setObjectName("productTabs")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # ══════════════════════════════════════════
        #  TAB 1: Customer Listing
        # ══════════════════════════════════════════
        listing_tab = QWidget()

        # Search row
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText(
            "Search by customer name, phone, email, city, address..."
        )
        self.search_edit.returnPressed.connect(self._search)

        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self._search)

        self.clear_search_button = QPushButton("Clear")
        self.clear_search_button.setObjectName("secondaryButton")
        self.clear_search_button.clicked.connect(self._clear_search)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(10, 8, 10, 8)
        search_row.setSpacing(8)
        search_row.addWidget(self.search_edit, stretch=1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.clear_search_button)

        search_panel = QWidget()
        search_panel.setObjectName("searchPanel")
        search_panel.setLayout(search_row)

        # Table
        self.table = QTableWidget(0, len(self._COLUMNS))
        self.table.setObjectName("productTable")
        self.table.setHorizontalHeaderLabels(list(self._COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(False)
        self.table.setCornerButtonEnabled(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Name stretches
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # Address stretches
        for column in (0, 2, 3, 4, 6, 7, 8, 9):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.doubleClicked.connect(self._open_selected_customer)
        self.table.keyPressEvent = self._table_key_press

        listing_layout = QVBoxLayout(listing_tab)
        listing_layout.setContentsMargins(12, 12, 12, 12)
        listing_layout.setSpacing(10)
        listing_layout.addWidget(search_panel)
        listing_layout.addWidget(self.table, stretch=1)

        self._tabs.addTab(listing_tab, "Customer Listing")

        # ══════════════════════════════════════════
        #  TAB 2: Add / Edit Customer Form
        # ══════════════════════════════════════════
        form_tab = QWidget()

        # Form fields
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Customer full name")

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("Phone / Mobile number")

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Email address (e.g. name@example.com)")

        self.city_edit = QLineEdit()
        self.city_edit.setPlaceholderText("City name")

        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("Street / Area address")

        self.balance_edit = QLineEdit()
        self.balance_edit.setPlaceholderText("0.00")

        self.credit_limit_edit = QLineEdit()
        self.credit_limit_edit.setPlaceholderText("Optional credit limit (0.00)")

        self.discount_edit = QLineEdit()
        self.discount_edit.setPlaceholderText("Discount percentage (0.00)")

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Additional notes or comments")

        self.active_check = QCheckBox("Customer is active")
        self.active_check.setChecked(True)

        # Form grid layout
        grid = QGridLayout()
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)

        row = 0

        # Section 1: General Info
        grid.addWidget(_make_section_title("GENERAL INFORMATION"), row, 0, 1, 2)
        grid.addWidget(_make_section_title("ADDRESS & LOCATION"), row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_separator(), row, 0, 1, 2)
        grid.addWidget(_make_separator(), row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_label("Customer Name *"), row, 0)
        grid.addWidget(_make_label("City"), row, 2)
        row += 1

        grid.addWidget(self.name_edit, row, 0, 1, 2)
        grid.addWidget(self.city_edit, row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_label("Phone Number"), row, 0)
        grid.addWidget(_make_label("Email Address"), row, 1)
        grid.addWidget(_make_label("Address"), row, 2, 1, 2)
        row += 1

        grid.addWidget(self.phone_edit, row, 0)
        grid.addWidget(self.email_edit, row, 1)
        grid.addWidget(self.address_edit, row, 2, 1, 2)
        row += 1

        # Spacing
        grid.addItem(QSpacerItem(0, 10), row, 0)
        row += 1

        # Section 2: Financial & Status
        grid.addWidget(_make_section_title("FINANCIAL DETAILS"), row, 0, 1, 2)
        grid.addWidget(_make_section_title("STATUS & NOTES"), row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_separator(), row, 0, 1, 2)
        grid.addWidget(_make_separator(), row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_label("Opening Balance"), row, 0)
        grid.addWidget(_make_label("Credit Limit"), row, 1)
        grid.addWidget(_make_label("Discount (%)"), row, 2)
        grid.addWidget(_make_label("Notes"), row, 3)
        row += 1

        grid.addWidget(self.balance_edit, row, 0)
        grid.addWidget(self.credit_limit_edit, row, 1)
        grid.addWidget(self.discount_edit, row, 2)
        grid.addWidget(self.notes_edit, row, 3)
        row += 1

        grid.addWidget(self.active_check, row, 0, 1, 2, Qt.AlignmentFlag.AlignVCenter)
        row += 1

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)

        form_card = QWidget()
        form_card.setObjectName("formCard")
        form_card.setLayout(grid)

        # Action Buttons
        self.new_button = QPushButton("New")
        self.new_button.setObjectName("secondaryButton")
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("successButton")
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setEnabled(False)

        self.new_button.clicked.connect(self._new_customer)
        self.save_button.clicked.connect(self._save)
        self.delete_button.clicked.connect(self._delete)

        for btn in (
            self.search_button,
            self.clear_search_button,
            self.new_button,
            self.save_button,
            self.delete_button,
        ):
            btn.setAutoDefault(False)
            btn.setDefault(False)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.setSpacing(10)
        buttons.addWidget(self.new_button)
        buttons.addWidget(self.save_button)
        buttons.addStretch(1)
        buttons.addWidget(self.delete_button)

        form_layout = QVBoxLayout(form_tab)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(10)
        form_layout.addWidget(form_card)
        form_layout.addLayout(buttons)
        form_layout.addStretch(1)

        self._tabs.addTab(form_tab, "Add / Edit Customer")

        # ── Main Layout ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addLayout(title_and_stats)
        layout.addWidget(self._tabs, stretch=1)

        self._reload()

    def _clear_search(self) -> None:
        self.search_edit.clear()
        self._reload()

    def _search(self) -> None:
        self._reload(select_id=self._customer_id)

    def _reload(self, select_id: int | None = None) -> None:
        customers = self._service.search(self.search_edit.text())
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(customers))

        for row, customer in enumerate(customers):
            values = [
                str(customer.id),
                customer.name or "",
                customer.phone or "",
                customer.email or "",
                customer.city or "",
                customer.address or "",
                f"{customer.opening_balance:.2f}" if customer.opening_balance is not None else "0.00",
                f"{customer.credit_limit:.2f}" if customer.credit_limit is not None else "",
                f"{customer.discount_percent:.2f}%" if customer.discount_percent is not None else "0.00%",
                "Yes" if customer.is_active else "No",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, customer.id)
                if col in (6, 7, 8):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, col, item)

        self.table.blockSignals(False)

        # Update stats
        stats = self._service.get_summary_stats()
        self.stat_total_label.setText(f"Total: {stats['total_count']}")
        self.stat_active_label.setText(f"Active: {stats['active_count']}")
        total_bal = stats['total_balance']
        self.stat_balance_label.setText(f"Total Balance: {total_bal:.2f}")

        if select_id is None:
            return
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == select_id:
                self.table.selectRow(r)
                return

    def _on_row_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid is None:
            return
        customer = self._service.get(int(cid))
        if customer is None:
            self._clear_editor()
            return
        self._load_customer(customer)

    def _open_selected_customer(self) -> None:
        """Switch to editor tab to edit selected customer."""
        if self._customer_id is not None:
            self._opening_customer = True
            try:
                self._tabs.setCurrentIndex(1)
            finally:
                self._opening_customer = False
            self.name_edit.setFocus()

    def _on_tab_changed(self, index: int) -> None:
        if self._opening_customer:
            return
        if self._customer_id is not None:
            self.table.blockSignals(True)
            self.table.clearSelection()
            self.table.blockSignals(False)
            self._clear_editor()

    def _table_key_press(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._open_selected_customer()
        else:
            QTableWidget.keyPressEvent(self.table, event)

    def _new_customer(self) -> None:
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.blockSignals(False)
        self._clear_editor()
        self.name_edit.setFocus()

    def _save(self) -> None:
        try:
            data = self._read_input()
        except (CustomerError, InvalidOperation) as exc:
            QMessageBox.warning(self, "Customer Error", str(exc))
            return

        try:
            with saving_indicator(self, self.save_button, message="Saving customer…", title="Customer"):
                if self._customer_id is None:
                    customer = self._service.create(data)
                else:
                    customer = self._service.update(self._customer_id, data)
        except (CustomerError, InvalidOperation) as exc:
            QMessageBox.warning(self, "Customer Error", str(exc))
            return

        self._reload(select_id=customer.id)
        # Switch back to customer listing tab
        self._tabs.setCurrentIndex(0)

    def _delete(self) -> None:
        if self._customer_id is None:
            return
        name = self.name_edit.text().strip() or "this customer"
        answer = QMessageBox.question(
            self,
            "Delete Customer",
            f"Are you sure you want to delete customer '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete(self._customer_id)
        except CustomerError as exc:
            QMessageBox.warning(self, "Customer Error", str(exc))
            return

        self._clear_editor()
        self._reload()
        self._tabs.setCurrentIndex(0)

    def _read_input(self) -> CustomerInput:
        balance = self._parse_decimal(
            self.balance_edit.text(), label="Opening Balance", default=Decimal("0.00")
        )
        credit_limit = self._parse_decimal(
            self.credit_limit_edit.text(), label="Credit Limit", default=None
        )
        discount = self._parse_decimal(
            self.discount_edit.text(), label="Discount (%)", default=Decimal("0.00")
        )
        return CustomerInput(
            name=self.name_edit.text(),
            phone=self.phone_edit.text(),
            email=self.email_edit.text(),
            city=self.city_edit.text(),
            address=self.address_edit.text(),
            opening_balance=balance,
            credit_limit=credit_limit,
            discount_percent=discount,
            notes=self.notes_edit.text(),
            is_active=self.active_check.isChecked(),
        )

    def _parse_decimal(
        self, text: str, *, label: str, default: Decimal | None
    ) -> Decimal | None:
        cleaned = text.strip()
        if not cleaned:
            return default
        try:
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise CustomerError(f"Enter a valid numeric value for {label}.") from exc

    def _load_customer(self, customer: Customer) -> None:
        self._customer_id = customer.id
        self.name_edit.setText(customer.name or "")
        self.phone_edit.setText(customer.phone or "")
        self.email_edit.setText(customer.email or "")
        self.city_edit.setText(customer.city or "")
        self.address_edit.setText(customer.address or "")
        self.balance_edit.setText(
            f"{customer.opening_balance:.2f}" if customer.opening_balance is not None else "0.00"
        )
        self.credit_limit_edit.setText(
            f"{customer.credit_limit:.2f}" if customer.credit_limit is not None else ""
        )
        self.discount_edit.setText(
            f"{customer.discount_percent:.2f}" if customer.discount_percent is not None else "0.00"
        )
        self.notes_edit.setText(customer.notes or "")
        self.active_check.setChecked(customer.is_active)
        self.delete_button.setEnabled(True)

    def _clear_editor(self) -> None:
        self._customer_id = None
        self.name_edit.clear()
        self.phone_edit.clear()
        self.email_edit.clear()
        self.city_edit.clear()
        self.address_edit.clear()
        self.balance_edit.clear()
        self.credit_limit_edit.clear()
        self.discount_edit.clear()
        self.notes_edit.clear()
        self.active_check.setChecked(True)
        self.delete_button.setEnabled(False)
