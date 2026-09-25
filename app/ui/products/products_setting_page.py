"""Dedicated page for product settings including translation and percentage-based price calculation."""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain.products.service import ProductError, ProductService


class ProductsSettingPage(QWidget):
    _MAX_PRODUCTS = 10

    def __init__(self, service: ProductService) -> None:
        super().__init__()
        self._service = service

        title = QLabel("Products Setting")
        title.setObjectName("pageTitle")

        self.tabs = QTabWidget()

        # Tab 1: Translation
        self.translation_tab = QWidget()
        self._setup_translation_tab()
        self.tabs.addTab(self.translation_tab, "Translation")

        # Tab 2: Price Calculation
        self.price_calc_tab = QWidget()
        self._setup_price_calc_tab()
        self.tabs.addTab(self.price_calc_tab, "Price Calculation")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self.tabs, stretch=1)

        self._reload_all()

    # ------------------------------------------------------------------
    # Tab 1: Translation Setup & Logic
    # ------------------------------------------------------------------
    def _setup_translation_tab(self) -> None:
        self.info = QLabel(
            "Select up to 10 products with a blank English name and Urdu description."
        )
        self.info.setWordWrap(True)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Select",
            "Manufacturer",
            "Model",
            "Urdu",
            "Current name",
        ])
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(self._select_all)
        self.translate_button = QPushButton("Translate selected")
        self.translate_button.clicked.connect(self._translate_selected)

        buttons = QHBoxLayout()
        buttons.addWidget(self.select_all_button)
        buttons.addStretch(1)
        buttons.addWidget(self.translate_button)

        tab_layout = QVBoxLayout(self.translation_tab)
        tab_layout.setContentsMargins(12, 12, 12, 12)
        tab_layout.setSpacing(12)
        tab_layout.addWidget(self.info)
        tab_layout.addLayout(buttons)
        tab_layout.addWidget(self.table, stretch=1)

    def _select_all(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)

    def _translate_selected(self) -> None:
        selected = self._selected_product_ids()
        if not selected:
            QMessageBox.information(
                self,
                "Translate Urdu",
                "Select at least one product to translate.",
            )
            return

        try:
            updated = self._service.translate_selected_missing_names(selected)
        except RuntimeError as exc:
            QMessageBox.warning(
                self,
                "Translate Urdu",
                f"{exc}\n\nWait 30-60 seconds and try again.",
            )
            return

        self._reload_all()
        QMessageBox.information(
            self,
            "Translate Urdu",
            f"Updated {updated} product name(s).",
        )

    def _selected_product_ids(self) -> list[int]:
        ids: list[int] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            product_id = item.data(Qt.ItemDataRole.UserRole)
            if product_id is not None:
                ids.append(int(product_id))
        return ids[: self._MAX_PRODUCTS]

    # ------------------------------------------------------------------
    # Tab 2: Price Calculation Setup & Logic
    # ------------------------------------------------------------------
    def _setup_price_calc_tab(self) -> None:
        calc_info = QLabel(
            "Enter percentage to calculate Sale Price based on Cost Price. You can also edit Sale Price directly in the table."
        )
        calc_info.setWordWrap(True)

        percent_label = QLabel("Percentage (%):")
        self.percent_edit = QLineEdit()
        self.percent_edit.setPlaceholderText("e.g. 15")
        self.percent_edit.setFixedWidth(110)
        self.percent_edit.returnPressed.connect(self._apply_percentage)

        self.apply_percent_button = QPushButton("Calculate Sale Price")
        self.apply_percent_button.clicked.connect(self._apply_percentage)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter products...")
        self.search_edit.textChanged.connect(self._filter_price_table)

        self.save_prices_button = QPushButton("Save Prices")
        self.save_prices_button.setObjectName("primaryButton")
        self.save_prices_button.clicked.connect(self._save_prices)

        controls = QHBoxLayout()
        controls.addWidget(percent_label)
        controls.addWidget(self.percent_edit)
        controls.addWidget(self.apply_percent_button)
        controls.addSpacing(16)
        controls.addWidget(self.search_edit)
        controls.addStretch(1)
        controls.addWidget(self.save_prices_button)

        self.price_table = QTableWidget(0, 6)
        self.price_table.setHorizontalHeaderLabels([
            "Product Name",
            "Urdu Name",
            "Manufacturer",
            "Model",
            "Cost Price",
            "Sale Price",
        ])
        self.price_table.setSelectionBehavior(self.price_table.SelectionBehavior.SelectRows)
        self.price_table.setSelectionMode(self.price_table.SelectionMode.SingleSelection)
        self.price_table.setAlternatingRowColors(True)
        self.price_table.verticalHeader().setVisible(False)

        tab_layout = QVBoxLayout(self.price_calc_tab)
        tab_layout.setContentsMargins(12, 12, 12, 12)
        tab_layout.setSpacing(12)
        tab_layout.addWidget(calc_info)
        tab_layout.addLayout(controls)
        tab_layout.addWidget(self.price_table, stretch=1)

    def _apply_percentage(self) -> None:
        raw_text = self.percent_edit.text().strip().rstrip("%")
        if not raw_text:
            QMessageBox.warning(
                self,
                "Price Calculation",
                "Please enter a percentage value (e.g. 15).",
            )
            return

        try:
            percentage = Decimal(raw_text)
        except InvalidOperation:
            QMessageBox.warning(
                self,
                "Price Calculation",
                "Please enter a valid numeric percentage.",
            )
            return

        factor = Decimal("1") + (percentage / Decimal("100"))

        for row in range(self.price_table.rowCount()):
            cost_item = self.price_table.item(row, 4)
            sale_item = self.price_table.item(row, 5)
            if cost_item is None or sale_item is None:
                continue

            cost_val = cost_item.data(Qt.ItemDataRole.UserRole)
            if cost_val is not None and isinstance(cost_val, Decimal) and cost_val >= 0:
                new_sale = (cost_val * factor).quantize(Decimal("0.01"))
                sale_item.setText(f"{new_sale:.2f}")

    def _filter_price_table(self, query: str) -> None:
        pattern = query.strip().lower()
        for row in range(self.price_table.rowCount()):
            match = False
            if not pattern:
                match = True
            else:
                for col in range(6):
                    item = self.price_table.item(row, col)
                    if item is not None and pattern in item.text().lower():
                        match = True
                        break
            self.price_table.setRowHidden(row, not match)

    def _save_prices(self) -> None:
        updates: list[tuple[int, Decimal | None]] = []

        for row in range(self.price_table.rowCount()):
            sale_item = self.price_table.item(row, 5)
            if sale_item is None:
                continue

            product_id = sale_item.data(Qt.ItemDataRole.UserRole)
            if product_id is None:
                continue

            sale_text = sale_item.text().strip()
            if not sale_text:
                sale_decimal = None
            else:
                try:
                    sale_decimal = Decimal(sale_text)
                except InvalidOperation:
                    name_item = self.price_table.item(row, 0)
                    p_name = name_item.text() if name_item else f"Row {row+1}"
                    QMessageBox.warning(
                        self,
                        "Save Prices",
                        f"Invalid sale price format '{sale_text}' for product '{p_name}'.",
                    )
                    return

            updates.append((int(product_id), sale_decimal))

        try:
            updated_count = self._service.update_sale_prices(updates)
            self._reload_all()
            QMessageBox.information(
                self,
                "Save Prices",
                f"Successfully updated sale prices for {updated_count} product(s).",
            )
        except ProductError as exc:
            QMessageBox.warning(self, "Save Prices", str(exc))

    # ------------------------------------------------------------------
    # Data Reloading
    # ------------------------------------------------------------------
    def _reload_all(self) -> None:
        self._reload_translation_table()
        self._reload_price_table()

    def _reload_translation_table(self) -> None:
        products = [
            product
            for product in self._service.search("")
            if self._service._is_missing_name(product.name)
            and (product.description_ur or product.model)
        ]

        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(products))

        for row, product in enumerate(products):
            checkbox = QTableWidgetItem()
            checkbox.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            checkbox.setData(Qt.ItemDataRole.UserRole, product.id)
            self.table.setItem(row, 0, checkbox)

            manufacturer = product.manufacturer.name if product.manufacturer else ""
            self.table.setItem(row, 1, QTableWidgetItem(manufacturer))
            self.table.setItem(row, 2, QTableWidgetItem(product.model or ""))
            self.table.setItem(row, 3, QTableWidgetItem(product.description_ur or ""))
            self.table.setItem(row, 4, QTableWidgetItem(product.name or ""))

        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for col in range(5):
            if col != 4:
                current_w = self.table.columnWidth(col)
                self.table.setColumnWidth(col, max(current_w + 30, 120))

    def _reload_price_table(self) -> None:
        products = self._service.search("")

        self.price_table.blockSignals(True)
        self.price_table.setRowCount(0)
        self.price_table.setRowCount(len(products))

        for row, product in enumerate(products):
            # 0: Product Name
            name_item = QTableWidgetItem(product.name or "")
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.price_table.setItem(row, 0, name_item)

            # 1: Urdu Name
            urdu_item = QTableWidgetItem(product.description_ur or "")
            urdu_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.price_table.setItem(row, 1, urdu_item)

            # 2: Manufacturer
            manufacturer = product.manufacturer.name if product.manufacturer else ""
            mfg_item = QTableWidgetItem(manufacturer)
            mfg_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.price_table.setItem(row, 2, mfg_item)

            # 3: Model
            model_item = QTableWidgetItem(product.model or "")
            model_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.price_table.setItem(row, 3, model_item)

            # 4: Cost Price (Read-only)
            cost_str = f"{product.cost_price:.2f}" if product.cost_price is not None else ""
            cost_item = QTableWidgetItem(cost_str)
            cost_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            cost_item.setData(Qt.ItemDataRole.UserRole, product.cost_price)
            self.price_table.setItem(row, 4, cost_item)

            # 5: Sale Price (Editable)
            sale_str = f"{product.unit_price:.2f}" if product.unit_price is not None else ""
            sale_item = QTableWidgetItem(sale_str)
            sale_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )
            sale_item.setData(Qt.ItemDataRole.UserRole, product.id)
            self.price_table.setItem(row, 5, sale_item)

        self.price_table.blockSignals(False)
        self.price_table.resizeColumnsToContents()

        header = self.price_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(6):
            if col != 0:
                current_w = self.price_table.columnWidth(col)
                min_w = 160 if col == 1 else 135
                self.price_table.setColumnWidth(col, max(current_w + 30, min_w))
