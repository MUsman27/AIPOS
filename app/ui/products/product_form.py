"""Product catalog form: search, edit, and barcode lookup."""

from decimal import Decimal, InvalidOperation

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpacerItem,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain.products.service import ProductError, ProductInput, ProductService
from app.infrastructure.database.models import Product
from app.infrastructure.database.session import get_session
from app.pdf_import.load import import_file
from app.ui.busy import saving_indicator

_URDU_FAMILIES = (
    "Noto Nastaliq Urdu",
    "Jameel Noori Nastaleeq",
    "Nafees Nastaleeq",
    "Microsoft Uighur",
    "Segoe UI",
)


def urdu_font() -> QFont:
    families = set(QFontDatabase.families())
    for name in _URDU_FAMILIES:
        if name in families:
            font = QFont(name)
            font.setPointSize(12 if name != "Segoe UI" else 10)
            return font
    return QFont("Segoe UI", 10)


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


class _PdfImportThread(QThread):
    succeeded = Signal(str, int, int)
    failed = Signal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        session = get_session()
        try:
            manufacturer, inserted, updated = import_file(session, Path(self._path))
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        finally:
            session.close()
        self.succeeded.emit(manufacturer, inserted, updated)


class ProductForm(QWidget):
    _COLUMNS = (
        "Manufacturer",
        "Code",
        "Model",
        "English",
        "Urdu",
        "Purchase",
        "Sale",
        "Active",
    )

    def __init__(self, service: ProductService) -> None:
        super().__init__()
        self._service = service
        self._product_id: int | None = None
        self._opening_product: bool = False
        self._urdu_font = urdu_font()
        self._import_thread: _PdfImportThread | None = None
        self._import_progress: QProgressDialog | None = None

        # ── Page Title ──
        title = QLabel("Products")
        title.setObjectName("pageTitle")

        subtitle = QLabel("Manage your product catalog, prices, and barcodes")
        subtitle.setObjectName("formLabel")

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        # ── Tab Widget ──
        self._tabs = QTabWidget()
        self._tabs.setObjectName("productTabs")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # ══════════════════════════════════════════
        #  TAB 1: Product Listing
        # ══════════════════════════════════════════
        listing_tab = QWidget()

        # Search row
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText(
            "Search by name, code, model, or manufacturer…"
        )
        self.search_edit.returnPressed.connect(self._search)

        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self._search)
        self.upload_button = QPushButton("Upload PDF")
        self.upload_button.setObjectName("secondaryButton")
        self.upload_button.clicked.connect(self._upload_pdf)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(10, 8, 10, 8)
        search_row.setSpacing(8)
        search_row.addWidget(self.search_edit, stretch=1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.upload_button)

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
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column in (0, 1, 2, 5, 6, 7):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.doubleClicked.connect(self._open_selected_product)
        self.table.keyPressEvent = self._table_key_press

        listing_layout = QVBoxLayout(listing_tab)
        listing_layout.setContentsMargins(12, 12, 12, 12)
        listing_layout.setSpacing(10)
        listing_layout.addWidget(search_panel)
        listing_layout.addWidget(self.table, stretch=1)

        self._tabs.addTab(listing_tab, "Product Listing")

        # ══════════════════════════════════════════
        #  TAB 2: Product Form
        # ══════════════════════════════════════════
        form_tab = QWidget()

        # Form fields
        self.manufacturer_edit = QComboBox()
        self.manufacturer_edit.setObjectName("productManufacturer")
        self.manufacturer_edit.setEditable(True)
        self.manufacturer_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.manufacturer_edit.setMinimumContentsLength(12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Product name in English")

        self.urdu_edit = QLineEdit()
        self.urdu_edit.setFont(self._urdu_font)
        self.urdu_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.urdu_edit.setPlaceholderText("اردو میں تفصیل")

        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("Model number")

        self.sku_edit = QLineEdit()
        self.sku_edit.setPlaceholderText("Unique item code")

        self.barcode_edit = QLineEdit()
        self.barcode_edit.setPlaceholderText("Scan or type barcode")
        self.barcode_edit.returnPressed.connect(self._on_barcode_entered)

        self.cost_edit = QLineEdit()
        self.cost_edit.setPlaceholderText("0.00")

        self.price_edit = QLineEdit()
        self.price_edit.setPlaceholderText("0.00")

        self.active_check = QCheckBox("Product is active")
        self.active_check.setChecked(True)

        # Two-column grid with sections
        grid = QGridLayout()
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)

        row = 0

        # Section: Identification
        grid.addWidget(_make_section_title("IDENTIFICATION"), row, 0, 1, 2)
        grid.addWidget(_make_section_title("DESCRIPTION"), row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_separator(), row, 0, 1, 2)
        grid.addWidget(_make_separator(), row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_label("Manufacturer"), row, 0)
        grid.addWidget(_make_label("English Name"), row, 2)
        row += 1

        grid.addWidget(self.manufacturer_edit, row, 0, 1, 2)
        grid.addWidget(self.name_edit, row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_label("Item Code"), row, 0)
        grid.addWidget(_make_label("Model"), row, 1)
        grid.addWidget(_make_label("Urdu Name"), row, 2, 1, 2)
        row += 1

        grid.addWidget(self.sku_edit, row, 0)
        grid.addWidget(self.model_edit, row, 1)
        grid.addWidget(self.urdu_edit, row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_label("Barcode"), row, 0, 1, 2)
        row += 1

        grid.addWidget(self.barcode_edit, row, 0, 1, 2)
        row += 1

        # Spacing
        grid.addItem(QSpacerItem(0, 8), row, 0)
        row += 1

        # Section: Pricing
        grid.addWidget(_make_section_title("PRICING"), row, 0, 1, 2)
        grid.addWidget(_make_section_title("STATUS"), row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_separator(), row, 0, 1, 2)
        grid.addWidget(_make_separator(), row, 2, 1, 2)
        row += 1

        grid.addWidget(_make_label("Purchase Price"), row, 0)
        grid.addWidget(_make_label("Sale Price"), row, 1)
        row += 1

        grid.addWidget(self.cost_edit, row, 0)
        grid.addWidget(self.price_edit, row, 1)
        grid.addWidget(self.active_check, row, 2, 1, 2, Qt.AlignmentFlag.AlignVCenter)
        row += 1

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)

        form_card = QWidget()
        form_card.setObjectName("formCard")
        form_card.setLayout(grid)

        # Action buttons
        self.new_button = QPushButton("New")
        self.new_button.setObjectName("secondaryButton")
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("successButton")
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setEnabled(False)
        self.new_button.clicked.connect(self._new_product)
        self.save_button.clicked.connect(self._save)
        self.delete_button.clicked.connect(self._delete)
        for button in (
            self.search_button,
            self.upload_button,
            self.new_button,
            self.save_button,
            self.delete_button,
        ):
            button.setAutoDefault(False)
            button.setDefault(False)

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

        self._tabs.addTab(form_tab, "Add / Edit Product")

        # ── Main Layout ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addLayout(title_block)
        layout.addWidget(self._tabs, stretch=1)

        self._reload()

    def _upload_pdf(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Upload price list",
            "",
            "PDF files (*.pdf)",
        )
        if not path:
            return
        self.upload_button.setEnabled(False)
        progress = QProgressDialog("Reading the price list...", None, 0, 0, self)
        progress.setWindowTitle("Upload PDF")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        self._import_progress = progress
        thread = _PdfImportThread(path)
        thread.succeeded.connect(self._on_import_finished)
        thread.failed.connect(self._on_import_failed)
        thread.finished.connect(thread.deleteLater)
        self._import_thread = thread
        thread.start()

    def _on_import_finished(self, manufacturer: str, inserted: int, updated: int) -> None:
        self._close_import_progress()
        self._service.session.expire_all()
        self._reload()
        QMessageBox.information(
            self,
            "Upload PDF",
            f"{manufacturer}: {inserted} new items, {updated} purchase prices updated. "
            "Sale prices were left unchanged.",
        )

    def _on_import_failed(self, message: str) -> None:
        self._close_import_progress()
        QMessageBox.warning(self, "Upload PDF", message)

    def _close_import_progress(self) -> None:
        self.upload_button.setEnabled(True)
        if self._import_progress is not None:
            self._import_progress.close()
            self._import_progress = None

    def _search(self) -> None:
        self._reload(select_id=self._product_id)

    def _reload(self, select_id: int | None = None) -> None:
        self._fill_manufacturers()
        products = self._service.search(self.search_edit.text())
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(products))
        for row, product in enumerate(products):
            manufacturer = product.manufacturer.name if product.manufacturer else ""
            values = [
                manufacturer,
                product.sku or "",
                product.model or "",
                product.name or "",
                product.description_ur or "",
                "" if product.cost_price is None else f"{product.cost_price:.2f}",
                "" if product.unit_price is None else f"{product.unit_price:.2f}",
                "Yes" if product.is_active else "No",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, product.id)
                if column == 4:
                    item.setFont(self._urdu_font)
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column in (5, 6):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)

        if select_id is None:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == select_id:
                self.table.selectRow(row)
                return

    def _fill_manufacturers(self) -> None:
        current = self.manufacturer_edit.currentText()
        self.manufacturer_edit.blockSignals(True)
        self.manufacturer_edit.clear()
        self.manufacturer_edit.addItem("")
        for manufacturer in self._service.list_manufacturers():
            self.manufacturer_edit.addItem(manufacturer.name)
        self.manufacturer_edit.setCurrentText(current)
        self.manufacturer_edit.blockSignals(False)

    def _on_row_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        product_id = item.data(Qt.ItemDataRole.UserRole)
        if product_id is None:
            return
        product = self._service.get(int(product_id))
        if product is None:
            self._clear_editor()
            return
        self._load_product(product)

    def _open_selected_product(self) -> None:
        """Switch to the form tab to edit the currently selected product."""
        if self._product_id is not None:
            self._opening_product = True
            try:
                self._tabs.setCurrentIndex(1)
            finally:
                self._opening_product = False
            self.name_edit.setFocus()

    def _on_tab_changed(self, index: int) -> None:
        if self._opening_product:
            return
        if self._product_id is not None:
            self.table.blockSignals(True)
            self.table.clearSelection()
            self.table.blockSignals(False)
            self._clear_editor()

    def _table_key_press(self, event: QKeyEvent) -> None:
        """Open product for editing on Enter/Return key."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._open_selected_product()
        else:
            QTableWidget.keyPressEvent(self.table, event)

    def _on_barcode_entered(self) -> None:
        product = self._service.get_by_barcode(self.barcode_edit.text())
        if product is None:
            return
        self.search_edit.clear()
        self._reload(select_id=product.id)

    def _new_product(self) -> None:
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.blockSignals(False)
        self._clear_editor()
        self.name_edit.setFocus()

    def _save(self) -> None:
        try:
            data = self._read_input()
        except ProductError as exc:
            QMessageBox.warning(self, "Product", str(exc))
            return

        try:
            with saving_indicator(self, self.save_button, message="Saving product…", title="Product"):
                if self._product_id is None:
                    product = self._service.create(data)
                else:
                    product = self._service.update(self._product_id, data)
        except ProductError as exc:
            QMessageBox.warning(self, "Product", str(exc))
            return

        self._reload(select_id=product.id)
        # Switch back to listing to show the result
        self._tabs.setCurrentIndex(0)

    def _delete(self) -> None:
        if self._product_id is None:
            return
        name = self.name_edit.text().strip() or "this product"
        answer = QMessageBox.question(
            self,
            "Delete product",
            f"Delete {name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete(self._product_id)
        except ProductError as exc:
            QMessageBox.warning(self, "Product", str(exc))
            return
        self._clear_editor()
        self._reload()
        self._tabs.setCurrentIndex(0)

    def _read_input(self) -> ProductInput:
        return ProductInput(
            name=self.name_edit.text(),
            sku=self.sku_edit.text(),
            barcode=self.barcode_edit.text(),
            unit_price=self._parse_price(
                self.price_edit.text(), required=False, label="Sale price"
            ),
            cost_price=self._parse_price(
                self.cost_edit.text(), required=False, label="Purchase price"
            ),
            is_active=self.active_check.isChecked(),
            description_ur=self.urdu_edit.text(),
            model=self.model_edit.text(),
            manufacturer_name=self.manufacturer_edit.currentText(),
        )

    def _parse_price(self, text: str, *, required: bool, label: str) -> Decimal | None:
        cleaned = text.strip()
        if not cleaned:
            if required:
                raise ProductError(f"{label} is required.")
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise ProductError(f"Enter a valid {label.lower()}.") from exc

    def _load_product(self, product: Product) -> None:
        self._product_id = product.id
        manufacturer = product.manufacturer.name if product.manufacturer else ""
        self.manufacturer_edit.setCurrentText(manufacturer)
        self.name_edit.setText(product.name or "")
        self.urdu_edit.setText(product.description_ur or "")
        self.model_edit.setText(product.model or "")
        self.sku_edit.setText(product.sku or "")
        self.barcode_edit.setText(product.barcode or "")
        self.price_edit.setText(
            "" if product.unit_price is None else f"{product.unit_price:.2f}"
        )
        self.cost_edit.setText(
            "" if product.cost_price is None else f"{product.cost_price:.2f}"
        )
        self.active_check.setChecked(product.is_active)
        self.delete_button.setEnabled(True)

    def _clear_editor(self) -> None:
        self._product_id = None
        self.manufacturer_edit.setCurrentText("")
        self.name_edit.clear()
        self.urdu_edit.clear()
        self.model_edit.clear()
        self.sku_edit.clear()
        self.barcode_edit.clear()
        self.price_edit.clear()
        self.cost_edit.clear()
        self.active_check.setChecked(True)
        self.delete_button.setEnabled(False)
