"""Sale form: POS terminal, invoice creation, cart checkout, receipt preview, and sales history."""

from decimal import Decimal, InvalidOperation
from typing import Sequence

from PySide6.QtCore import QEvent, QMarginsF, QObject, QSize, QSizeF, Qt
from PySide6.QtGui import (
    QFont,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QPageLayout,
    QPageSize,
    QShortcut,
    QShowEvent,
    QTextDocument,
    QTextOption,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.domain.customers.service import CustomerService
from app.domain.products.service import ProductService
from app.domain.sales.service import SaleError, SaleInput, SaleItemInput, SaleService
from app.infrastructure.database.models import Customer, Product, Sale
from app.invoicing import render_a4_html, render_thermal_text
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


class ReceiptDialog(QDialog):
    """Modal dialog for thermal (80mm) and A4 invoice receipt formats."""

    _FORMAT_THERMAL = "thermal"
    _FORMAT_A4 = "a4"

    # Narrow 80mm thermal layout (~38 chars).
    _THERMAL = {
        "width": 38,
        "item_w": 19,
        "qty_w": 4,
        "price_w": 7,
        "amount_w": 8,
        "font_pt": 9,
    }
    # A4 uses HTML tables (not monospace padding) so print won't wrap columns.
    _A4 = {
        "font_pt": 11,
    }

    def __init__(self, sale: Sale, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sale = sale
        self._format = self._FORMAT_THERMAL
        self.setWindowTitle(f"Receipt - {sale.invoice_number}")
        self.resize(640, 760)
        self.setMinimumSize(480, 540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        format_row = QHBoxLayout()
        format_row.setSpacing(8)
        format_label = QLabel("Format")
        format_label.setObjectName("formLabel")
        format_row.addWidget(format_label)

        self.format_combo = QComboBox()
        self.format_combo.addItem("Thermal 80mm", self._FORMAT_THERMAL)
        self.format_combo.addItem("A4 Invoice", self._FORMAT_A4)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        format_row.addWidget(self.format_combo, stretch=1)
        layout.addLayout(format_row)

        self.receipt_view = QTextEdit()
        self.receipt_view.setReadOnly(True)
        layout.addWidget(self.receipt_view, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        print_thermal_btn = QPushButton("Print Thermal")
        print_thermal_btn.setObjectName("primaryButton")
        print_thermal_btn.clicked.connect(self._print_thermal)
        btn_layout.addWidget(print_thermal_btn)

        print_a4_btn = QPushButton("Print A4")
        print_a4_btn.setObjectName("secondaryButton")
        print_a4_btn.clicked.connect(self._print_a4)
        btn_layout.addWidget(print_a4_btn)

        btn_layout.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        self._refresh_preview()

    def _mono_font(self, point_size: int) -> QFont:
        mono = QFont("Consolas", point_size)
        if not mono.exactMatch():
            mono = QFont("Courier New", point_size)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setFixedPitch(True)
        return mono

    def _on_format_changed(self) -> None:
        self._format = self.format_combo.currentData()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._format == self._FORMAT_A4:
            self.receipt_view.setStyleSheet("")
            self.receipt_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            self.receipt_view.setFont(QFont("Segoe UI", 10))
            self.receipt_view.setHtml(render_a4_html(self._sale))
        else:
            # Stylesheet must force mono — global theme Segoe UI breaks column padding.
            mono = self._mono_font(self._THERMAL["font_pt"] + 1)
            self.receipt_view.setStyleSheet(
                f'font-family: "{mono.family()}", "Courier New", monospace;'
                f"font-size: {mono.pointSize()}pt;"
            )
            self.receipt_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.receipt_view.setFont(mono)
            self.receipt_view.document().setDefaultFont(mono)
            option = QTextOption()
            option.setWrapMode(QTextOption.WrapMode.NoWrap)
            self.receipt_view.document().setDefaultTextOption(option)
            self.receipt_view.setPlainText(render_thermal_text(self._sale))

    def _make_document(self, fmt: str, page_width: float | None = None) -> QTextDocument:
        document = QTextDocument()
        document.setDocumentMargin(0)
        if fmt == self._FORMAT_A4:
            document.setDefaultFont(QFont("Segoe UI", self._A4["font_pt"]))
            document.setHtml(render_a4_html(self._sale))
            if page_width and page_width > 0:
                document.setTextWidth(page_width)
        else:
            document.setDefaultFont(self._mono_font(self._THERMAL["font_pt"]))
            # Keep thermal lines intact — do not wrap on spaces.
            option = QTextOption()
            option.setWrapMode(QTextOption.WrapMode.NoWrap)
            document.setDefaultTextOption(option)
            document.setPlainText(render_thermal_text(self._sale))
            document.setTextWidth(-1)
        return document

    def _configure_thermal_printer(self, printer: QPrinter) -> None:
        # 80mm roll; tall page so multi-item receipts fit on one print page.
        page_size = QPageSize(QSizeF(80, 297), QPageSize.Unit.Millimeter, "Thermal80")
        layout = QPageLayout(
            page_size,
            QPageLayout.Orientation.Portrait,
            QMarginsF(3, 3, 3, 3),
            QPageLayout.Unit.Millimeter,
        )
        printer.setPageLayout(layout)

    def _configure_a4_printer(self, printer: QPrinter) -> None:
        page_size = QPageSize(QPageSize.PageSizeId.A4)
        layout = QPageLayout(
            page_size,
            QPageLayout.Orientation.Portrait,
            QMarginsF(10, 12, 10, 12),
            QPageLayout.Unit.Millimeter,
        )
        printer.setPageLayout(layout)

    def _print_with_dialog(self, fmt: str, title: str) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if fmt == self._FORMAT_THERMAL:
            self._configure_thermal_printer(printer)
        else:
            self._configure_a4_printer(printer)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle(title)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        # Re-apply layout after the dialog (Windows often switches to Letter).
        if fmt == self._FORMAT_THERMAL:
            self._configure_thermal_printer(printer)
        else:
            self._configure_a4_printer(printer)
        # Use point units so HighResolution DPI doesn't shrink the layout.
        page_width = float(printer.pageRect(QPrinter.Unit.Point).width())
        self._make_document(fmt, page_width=page_width).print_(printer)

    def _print_thermal(self) -> None:
        self._print_with_dialog(self._FORMAT_THERMAL, "Print Thermal Receipt")

    def _print_a4(self) -> None:
        self._print_with_dialog(self._FORMAT_A4, "Print A4 Invoice")


class SaleForm(QWidget):
    """Point of Sale UI widget supporting product selection, cart operations, customer checkout, and sales history."""

    _CATALOG_COLS = ("Code / Barcode", "Product Name", "Model", "Price")
    _HISTORY_COLS = ("Invoice #", "Date", "Customer", "Items", "Total Amount", "Paid", "Status", "Method")

    def __init__(
        self,
        sale_service: SaleService,
        product_service: ProductService,
        customer_service: CustomerService,
    ) -> None:
        super().__init__()
        self._sale_service = sale_service
        self._product_service = product_service
        self._customer_service = customer_service

        # Cart state: list of dicts {"product_id", "product_name", "sku", "barcode", "unit_price", "cost_price", "quantity", "discount_amount"}
        self._cart: list[dict] = []
        self._cart_qty_edits: list[QLineEdit] = []
        self._cart_total_labels: list[QLabel] = []
        self._customers_list: list[Customer] = []
        self._products_list: list[Product] = []

        self._init_ui()
        self._setup_shortcuts()
        self.reload_data()

    def reload_data(self) -> None:
        """Refresh customer dropdown, product catalog, and sales history."""
        self._sale_service.session.expire_all()
        self._load_customers()
        self._load_products()
        self._load_history()
        self._update_stats()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # Refresh catalog/customers when navigating back from Products/Customers
        if getattr(self, "customer_combo", None) is not None:
            self.reload_data()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── Title & Summary Metrics Header ──
        title = QLabel("Sales Terminal")
        title.setObjectName("pageTitle")

        subtitle = QLabel("Process POS checkout, manage customer invoices, and view transaction history")
        subtitle.setObjectName("formLabel")

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        # Metrics stats
        self.stat_count_label = QLabel("Total Sales: 0")
        self.stat_count_label.setObjectName("formLabel")

        self.stat_revenue_label = QLabel("Total Revenue: $0.00")
        self.stat_revenue_label.setObjectName("formLabel")

        self.stat_unpaid_label = QLabel("Unpaid Receivables: $0.00")
        self.stat_unpaid_label.setObjectName("formLabel")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        stats_row.addWidget(self.stat_count_label)
        stats_row.addWidget(self.stat_revenue_label)
        stats_row.addWidget(self.stat_unpaid_label)
        stats_row.addStretch(1)

        header_layout = QHBoxLayout()
        header_layout.addLayout(title_block, stretch=1)
        header_layout.addLayout(stats_row)

        main_layout.addLayout(header_layout)

        # ── Tabs ──
        self._tabs = QTabWidget()
        self._tabs.setObjectName("productTabs")

        # ══════════════════════════════════════════
        # TAB 1: New Sale (POS Terminal)
        # ══════════════════════════════════════════
        pos_tab = QWidget()
        pos_layout = QVBoxLayout(pos_tab)
        pos_layout.setContentsMargins(8, 8, 8, 8)
        pos_layout.setSpacing(10)

        # Customer & Invoice Header Bar
        cust_bar = QWidget()
        cust_bar.setObjectName("searchPanel")
        cust_layout = QHBoxLayout(cust_bar)
        cust_layout.setContentsMargins(12, 8, 12, 8)
        cust_layout.setSpacing(12)

        cust_label = QLabel("Customer:")
        cust_label.setObjectName("formLabel")
        self.customer_combo = QComboBox()
        self.customer_combo.setMinimumWidth(220)
        self.customer_combo.currentIndexChanged.connect(self._on_customer_changed)

        self.customer_info_label = QLabel("Walk-in / Cash Customer")
        self.customer_info_label.setStyleSheet("color: #6366f1; font-weight: 600;")

        self.invoice_no_label = QLabel("Invoice: Auto")
        self.invoice_no_label.setStyleSheet("font-weight: 700; color: #16a34a;")

        cust_layout.addWidget(cust_label)
        cust_layout.addWidget(self.customer_combo, stretch=1)
        cust_layout.addWidget(self.customer_info_label)
        cust_layout.addSpacing(20)
        cust_layout.addWidget(self.invoice_no_label)

        pos_layout.addWidget(cust_bar)

        # Splitter: Catalog (Left) vs Cart (Right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- LEFT PANEL: Product Search & Catalog ---
        catalog_widget = QWidget()
        catalog_layout = QVBoxLayout(catalog_widget)
        catalog_layout.setContentsMargins(0, 0, 0, 0)
        catalog_layout.setSpacing(8)

        # Search Bar
        self.product_search_edit = QLineEdit()
        self.product_search_edit.setObjectName("searchField")
        self.product_search_edit.setPlaceholderText("Search product by name, SKU, or barcode...")
        self.product_search_edit.textChanged.connect(self._filter_products)
        self.product_search_edit.installEventFilter(self)

        search_box = QHBoxLayout()
        search_box.addWidget(self.product_search_edit, stretch=1)

        catalog_layout.addLayout(search_box)

        # Products Table
        self.catalog_table = QTableWidget(0, len(self._CATALOG_COLS))
        self.catalog_table.setObjectName("productTable")
        self.catalog_table.setHorizontalHeaderLabels(list(self._CATALOG_COLS))
        self.catalog_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.catalog_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.catalog_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.catalog_table.setAlternatingRowColors(True)
        self.catalog_table.verticalHeader().setVisible(False)
        self.catalog_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.catalog_table.doubleClicked.connect(self._on_catalog_double_clicked)
        self.catalog_table.installEventFilter(self)

        catalog_layout.addWidget(self.catalog_table, stretch=1)

        # Manual Custom Line Item Box
        custom_box = QWidget()
        custom_box.setObjectName("formCard")
        custom_layout = QHBoxLayout(custom_box)
        custom_layout.setContentsMargins(10, 8, 10, 8)
        custom_layout.setSpacing(8)

        self.custom_name_edit = QLineEdit()
        self.custom_name_edit.setPlaceholderText("Custom Item Name")

        self.custom_price_edit = QLineEdit()
        self.custom_price_edit.setPlaceholderText("Price ($)")
        self.custom_price_edit.setFixedWidth(90)

        self.add_custom_button = QPushButton("+ Custom Item")
        self.add_custom_button.setObjectName("secondaryButton")
        self.add_custom_button.setFixedHeight(30)
        self.add_custom_button.setStyleSheet("min-width: 0px; min-height: 0px; padding: 4px 10px; font-size: 12px;")
        self.add_custom_button.clicked.connect(self._add_custom_item_to_cart)

        custom_layout.addWidget(self.custom_name_edit, stretch=1)
        custom_layout.addWidget(self.custom_price_edit)
        custom_layout.addWidget(self.add_custom_button)

        catalog_layout.addWidget(custom_box)

        # --- RIGHT PANEL: Cart & Billing Card ---
        cart_widget = QWidget()
        cart_widget.setObjectName("formCard")
        cart_layout = QVBoxLayout(cart_widget)
        cart_layout.setContentsMargins(12, 12, 12, 12)
        cart_layout.setSpacing(8)

        cart_title_row = QHBoxLayout()
        cart_title = QLabel("CURRENT ORDER CART")
        cart_title.setObjectName("formSectionTitle")

        self.clear_cart_button = QPushButton("Clear Cart")
        self.clear_cart_button.setObjectName("secondaryButton")
        self.clear_cart_button.setFixedHeight(28)
        self.clear_cart_button.clicked.connect(self._clear_cart)

        cart_title_row.addWidget(cart_title, stretch=1)
        cart_title_row.addWidget(self.clear_cart_button)

        cart_layout.addLayout(cart_title_row)

        # Column header for cart list
        cart_header = QWidget()
        cart_header.setObjectName("cartListHeader")
        cart_header_layout = QHBoxLayout(cart_header)
        cart_header_layout.setContentsMargins(8, 4, 8, 4)
        cart_header_layout.setSpacing(8)

        def _cart_col_label(text: str, width: int | None = None, stretch: int = 0) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("formLabel")
            if width is not None:
                lbl.setFixedWidth(width)
            if stretch:
                cart_header_layout.addWidget(lbl, stretch=stretch)
            else:
                cart_header_layout.addWidget(lbl)
            return lbl

        _cart_col_label("#", 28)
        _cart_col_label("Item", stretch=1)
        _cart_col_label("Price", 72)
        _cart_col_label("Qty", 72)
        _cart_col_label("Total", 80)
        _cart_col_label("", 28)
        cart_layout.addWidget(cart_header)

        # Scrollable cart item list (inputs/labels — not a table)
        self.cart_scroll = QScrollArea()
        self.cart_scroll.setObjectName("cartScroll")
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cart_list_host = QWidget()
        self.cart_list_host.setObjectName("cartListHost")
        self.cart_list_layout = QVBoxLayout(self.cart_list_host)
        self.cart_list_layout.setContentsMargins(0, 0, 0, 0)
        self.cart_list_layout.setSpacing(6)
        self.cart_list_layout.addStretch(1)

        self.cart_scroll.setWidget(self.cart_list_host)
        cart_layout.addWidget(self.cart_scroll, stretch=1)

        # Billing Breakdown
        billing_grid = QGridLayout()
        billing_grid.setContentsMargins(4, 4, 4, 4)
        billing_grid.setHorizontalSpacing(12)
        billing_grid.setVerticalSpacing(6)

        b_row = 0
        billing_grid.addWidget(_make_label("Subtotal:"), b_row, 0)
        self.subtotal_val_label = QLabel("0.00")
        self.subtotal_val_label.setStyleSheet("font-weight: 600;")
        billing_grid.addWidget(self.subtotal_val_label, b_row, 1)

        b_row += 1
        billing_grid.addWidget(_make_label("Discount:"), b_row, 0)
        self.discount_edit = QLineEdit("0.00")
        self.discount_edit.setFixedWidth(100)
        self.discount_edit.textChanged.connect(self._recalculate_totals)
        self.discount_edit.returnPressed.connect(lambda: self._focus_field(self.tax_edit))
        billing_grid.addWidget(self.discount_edit, b_row, 1)

        b_row += 1
        billing_grid.addWidget(_make_label("Tax:"), b_row, 0)
        self.tax_edit = QLineEdit("0.00")
        self.tax_edit.setFixedWidth(100)
        self.tax_edit.textChanged.connect(self._recalculate_totals)
        self.tax_edit.returnPressed.connect(lambda: self._focus_field(self.paid_edit))
        billing_grid.addWidget(self.tax_edit, b_row, 1)

        b_row += 1
        billing_grid.addWidget(_make_separator(), b_row, 0, 1, 2)

        b_row += 1
        total_lbl = QLabel("GRAND TOTAL:")
        total_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #6366f1;")
        self.grand_total_label = QLabel("$0.00")
        self.grand_total_label.setStyleSheet("font-size: 20px; font-weight: 800; color: #6366f1;")

        billing_grid.addWidget(total_lbl, b_row, 0)
        billing_grid.addWidget(self.grand_total_label, b_row, 1)

        b_row += 1
        billing_grid.addWidget(_make_separator(), b_row, 0, 1, 2)

        b_row += 1
        billing_grid.addWidget(_make_label("Payment Method:"), b_row, 0)
        self.payment_method_combo = QComboBox()
        self.payment_method_combo.addItems(["Cash", "Card", "Bank Transfer", "Credit"])
        billing_grid.addWidget(self.payment_method_combo, b_row, 1)

        b_row += 1
        billing_grid.addWidget(_make_label("Paid Amount:"), b_row, 0)
        self.paid_edit = QLineEdit("0.00")
        self.paid_edit.setFixedWidth(100)
        self.paid_edit.textChanged.connect(self._recalculate_totals)
        billing_grid.addWidget(self.paid_edit, b_row, 1)

        b_row += 1
        billing_grid.addWidget(_make_label("Change / Due:"), b_row, 0)
        self.change_val_label = QLabel("0.00")
        self.change_val_label.setStyleSheet("font-weight: 700; color: #16a34a;")
        billing_grid.addWidget(self.change_val_label, b_row, 1)

        cart_layout.addLayout(billing_grid)
        self._refresh_cart_view()

        # Checkout Buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.complete_sale_button = QPushButton("Complete Sale (Checkout)")
        self.complete_sale_button.setObjectName("primaryButton")
        self.complete_sale_button.setFixedHeight(38)
        self.complete_sale_button.clicked.connect(self._complete_sale)

        action_row.addWidget(self.complete_sale_button, stretch=1)

        cart_layout.addLayout(action_row)

        splitter.addWidget(catalog_widget)
        splitter.addWidget(cart_widget)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)

        pos_layout.addWidget(splitter, stretch=1)
        self._tabs.addTab(pos_tab, "POS Checkout")

        # ══════════════════════════════════════════
        # TAB 2: Sales History & Orders
        # ══════════════════════════════════════════
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.setContentsMargins(12, 12, 12, 12)
        history_layout.setSpacing(10)

        # Search bar for history
        search_history_row = QHBoxLayout()
        search_history_row.setSpacing(8)

        self.history_search_edit = QLineEdit()
        self.history_search_edit.setObjectName("searchField")
        self.history_search_edit.setPlaceholderText("Search by invoice #, customer name, status...")
        self.history_search_edit.returnPressed.connect(self._search_history)

        search_hist_btn = QPushButton("Search")
        search_hist_btn.setObjectName("primaryButton")
        search_hist_btn.clicked.connect(self._search_history)

        clear_hist_btn = QPushButton("Clear")
        clear_hist_btn.setObjectName("secondaryButton")
        clear_hist_btn.clicked.connect(self._clear_history_search)

        search_history_row.addWidget(self.history_search_edit, stretch=1)
        search_history_row.addWidget(search_hist_btn)
        search_history_row.addWidget(clear_hist_btn)

        history_search_panel = QWidget()
        history_search_panel.setObjectName("searchPanel")
        history_search_panel.setLayout(search_history_row)

        history_layout.addWidget(history_search_panel)

        # Sales History Table
        self.history_table = QTableWidget(0, len(self._HISTORY_COLS))
        self.history_table.setObjectName("productTable")
        self.history_table.setHorizontalHeaderLabels(list(self._HISTORY_COLS))
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for c in (0, 1, 3, 4, 5, 6, 7):
            self.history_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        self.history_table.doubleClicked.connect(self._view_selected_receipt)

        history_layout.addWidget(self.history_table, stretch=1)

        # Bottom Actions for History
        history_action_row = QHBoxLayout()
        history_action_row.setSpacing(10)

        self.view_receipt_btn = QPushButton("View Receipt")
        self.view_receipt_btn.setObjectName("primaryButton")
        self.view_receipt_btn.clicked.connect(self._view_selected_receipt)

        self.void_sale_btn = QPushButton("Void / Cancel Sale")
        self.void_sale_btn.setObjectName("dangerButton")
        self.void_sale_btn.clicked.connect(self._void_selected_sale)

        history_action_row.addWidget(self.view_receipt_btn)
        history_action_row.addWidget(self.void_sale_btn)
        history_action_row.addStretch(1)

        history_layout.addLayout(history_action_row)

        self._tabs.addTab(history_tab, "Sales History")

        main_layout.addWidget(self._tabs, stretch=1)

    # ── Data Loading & Event Handlers ──

    def _load_customers(self) -> None:
        selected_id = self.customer_combo.currentData()
        self.customer_combo.blockSignals(True)
        self.customer_combo.clear()
        self.customer_combo.addItem("Walk-in Customer (Cash)", userData=None)

        self._customers_list = self._customer_service.search("")
        for cust in self._customers_list:
            if cust.is_active:
                disc_str = f" ({cust.discount_percent:.0f}% OFF)" if (cust.discount_percent and cust.discount_percent > 0) else ""
                self.customer_combo.addItem(f"{cust.name}{disc_str}", userData=cust.id)

        if selected_id is not None:
            idx = self.customer_combo.findData(selected_id)
            if idx >= 0:
                self.customer_combo.setCurrentIndex(idx)

        self.customer_combo.blockSignals(False)
        self._on_customer_changed(apply_discount=False)

    def _load_products(self) -> None:
        self._products_list = self._product_service.search("")
        self._filter_products(self.product_search_edit.text())

    def _filter_products(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            filtered = self._products_list
        else:
            filtered = [
                p for p in self._products_list
                if (p.name and query in p.name.lower())
                or (p.sku and query in p.sku.lower())
                or (p.barcode and query in p.barcode.lower())
                or (p.model and query in p.model.lower())
            ]
        self._populate_catalog(filtered)

    def _populate_catalog(self, products: list[Product]) -> None:
        self.catalog_table.setRowCount(0)
        for p in products:
            if not p.is_active:
                continue
            row = self.catalog_table.rowCount()
            self.catalog_table.insertRow(row)

            code_text = p.barcode or p.sku or "-"
            self.catalog_table.setItem(row, 0, QTableWidgetItem(code_text))

            name_item = QTableWidgetItem(p.name or "")
            name_item.setData(Qt.ItemDataRole.UserRole, p.id)
            self.catalog_table.setItem(row, 1, name_item)

            self.catalog_table.setItem(row, 2, QTableWidgetItem(p.model or "-"))

            price_val = f"${p.unit_price:.2f}" if p.unit_price is not None else "$0.00"
            self.catalog_table.setItem(row, 3, QTableWidgetItem(price_val))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if watched is self.product_search_edit and event.key() == Qt.Key.Key_Down:
                if self.catalog_table.rowCount() > 0:
                    self.catalog_table.setFocus()
                    self.catalog_table.selectRow(0)
                    return True
            if watched is self.catalog_table:
                if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                    self._on_catalog_double_clicked()
                    return True
                if event.key() == Qt.Key.Key_Up and self.catalog_table.currentRow() <= 0:
                    self.product_search_edit.setFocus()
                    self.product_search_edit.selectAll()
                    return True
            if watched in self._cart_qty_edits and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                index = self._cart_qty_edits.index(watched)  # type: ignore[arg-type]
                delta = -1 if event.key() == Qt.Key.Key_Up else 1
                self._move_qty_focus(index, delta)
                return True
        return super().eventFilter(watched, event)

    def _on_catalog_double_clicked(self) -> None:
        row = self.catalog_table.currentRow()
        if row >= 0:
            name_item = self.catalog_table.item(row, 1)
            if name_item:
                prod_id = name_item.data(Qt.ItemDataRole.UserRole)
                prod = self._product_service.get(prod_id)
                if prod:
                    self._add_product_to_cart(prod)

    def _add_product_to_cart(self, product: Product) -> None:
        unit_price = product.unit_price or Decimal("0.00")
        # Check if already in cart
        for item in self._cart:
            if item["product_id"] == product.id:
                item["quantity"] += Decimal("1.00")
                self._refresh_cart_view()
                return

        self._cart.append({
            "product_id": product.id,
            "product_name": product.name or "Unnamed Product",
            "sku": product.sku,
            "barcode": product.barcode,
            "unit_price": unit_price,
            "cost_price": product.cost_price,
            "quantity": Decimal("1.00"),
            "discount_amount": Decimal("0.00"),
        })
        self._refresh_cart_view()

    def _add_custom_item_to_cart(self) -> None:
        name = self.custom_name_edit.text().strip()
        price_text = self.custom_price_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Invalid Item", "Please enter a custom item name.")
            return
        try:
            price = Decimal(price_text) if price_text else Decimal("0.00")
        except InvalidOperation:
            QMessageBox.warning(self, "Invalid Price", "Please enter a valid price amount.")
            return

        self._cart.append({
            "product_id": None,
            "product_name": name,
            "sku": None,
            "barcode": None,
            "unit_price": price,
            "cost_price": None,
            "quantity": Decimal("1.00"),
            "discount_amount": Decimal("0.00"),
        })
        self.custom_name_edit.clear()
        self.custom_price_edit.clear()
        self._refresh_cart_view()

    def _on_customer_changed(self, *_args, apply_discount: bool = True) -> None:
        cust_id = self.customer_combo.currentData()
        if cust_id is None:
            self.customer_info_label.setText("Walk-in / Cash Customer")
            self.customer_info_label.setStyleSheet("color: #6366f1; font-weight: 600;")
            return
        cust = self._customer_service.get(cust_id)
        if not cust:
            return
        info = f"Phone: {cust.phone or 'N/A'} | Balance: ${cust.opening_balance:.2f}"
        if cust.discount_percent and cust.discount_percent > 0:
            info += f" | Disc: {cust.discount_percent:.0f}%"
            if apply_discount:
                self._apply_customer_default_discount(cust.discount_percent)
        self.customer_info_label.setText(info)
        self.customer_info_label.setStyleSheet("color: #16a34a; font-weight: 600;")

    def _apply_customer_default_discount(self, disc_pct: Decimal) -> None:
        subtotal = sum((item["unit_price"] * item["quantity"] for item in self._cart), Decimal("0.00"))
        if subtotal > Decimal("0.00"):
            disc_amt = (subtotal * (disc_pct / Decimal("100"))).quantize(Decimal("0.01"))
            self.discount_edit.setText(f"{disc_amt:.2f}")

    def _setup_shortcuts(self) -> None:
        search_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        search_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        search_shortcut.activated.connect(self._focus_product_search)

        qty_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        qty_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        qty_shortcut.activated.connect(self._focus_cart_qty)

    def _focus_product_search(self) -> None:
        self._tabs.setCurrentIndex(0)
        self.product_search_edit.setFocus()
        self.product_search_edit.selectAll()

    def _is_focus_in_cart_area(self) -> bool:
        focused = QApplication.focusWidget()
        if focused is None:
            return False
        if focused in self._cart_qty_edits:
            return True
        host = getattr(self, "cart_list_host", None)
        scroll = getattr(self, "cart_scroll", None)
        parent = focused
        while parent is not None:
            if parent is host or parent is scroll:
                return True
            parent = parent.parentWidget()
        return False

    def _focus_cart_qty(self) -> None:
        if not self._cart_qty_edits:
            return
        if self._is_focus_in_cart_area():
            return
        self._tabs.setCurrentIndex(0)
        self._focus_field(self._cart_qty_edits[0])

    def _focus_field(self, field: QLineEdit) -> None:
        field.setFocus()
        field.selectAll()

    def _fmt_qty(self, qty: Decimal) -> str:
        if qty == qty.to_integral_value():
            return str(int(qty))
        return f"{qty:.2f}"

    def _clear_cart_list_widgets(self) -> None:
        while self.cart_list_layout.count():
            item = self.cart_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_cart_view(self) -> None:
        self._clear_cart_list_widgets()
        self._cart_qty_edits = []
        self._cart_total_labels = []

        if not self._cart:
            empty = QLabel("Cart is empty — search and add products")
            empty.setObjectName("formLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(80)
            self.cart_list_layout.addWidget(empty)
            self.cart_list_layout.addStretch(1)
            self._recalculate_totals()
            return

        for idx, item in enumerate(self._cart):
            self.cart_list_layout.addWidget(self._build_cart_row(idx, item))

        self.cart_list_layout.addStretch(1)
        self._recalculate_totals()

    def _build_cart_row(self, index: int, item: dict) -> QWidget:
        row = QWidget()
        row.setObjectName("cartItemRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        num_lbl = QLabel(str(index + 1))
        num_lbl.setFixedWidth(28)
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_lbl.setStyleSheet("background: transparent; font-weight: 600;")

        name_lbl = QLabel(item["product_name"])
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet("background: transparent; font-weight: 600;")

        price_lbl = QLabel(f"${item['unit_price']:.2f}")
        price_lbl.setFixedWidth(72)
        price_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        price_lbl.setStyleSheet("background: transparent;")

        line_total = item["unit_price"] * item["quantity"]
        total_lbl = QLabel(f"${line_total:.2f}")
        total_lbl.setFixedWidth(80)
        total_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        total_lbl.setStyleSheet("background: transparent; font-weight: 700;")

        qty_edit = QLineEdit(self._fmt_qty(item["quantity"]))
        qty_edit.setFixedWidth(72)
        qty_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qty_edit.setToolTip("Type quantity, Enter for next field")
        qty_edit.editingFinished.connect(
            lambda i=index, edit=qty_edit, tot=total_lbl: self._on_cart_qty_edited(i, edit, tot)
        )
        qty_edit.returnPressed.connect(lambda i=index: self._on_qty_enter(i))
        qty_edit.installEventFilter(self)

        rem_btn = QPushButton("✕")
        rem_btn.setObjectName("dangerButton")
        rem_btn.setFixedSize(28, 28)
        rem_btn.setStyleSheet(
            "min-width: 0px; min-height: 0px; padding: 0px; font-size: 12px; font-weight: bold; border-radius: 4px;"
        )
        rem_btn.clicked.connect(lambda _, i=index: self._remove_from_cart(i))

        layout.addWidget(num_lbl)
        layout.addWidget(name_lbl, stretch=1)
        layout.addWidget(price_lbl)
        layout.addWidget(qty_edit)
        layout.addWidget(total_lbl)
        layout.addWidget(rem_btn)

        self._cart_qty_edits.append(qty_edit)
        self._cart_total_labels.append(total_lbl)
        return row

    def _on_qty_enter(self, index: int) -> None:
        if not (0 <= index < len(self._cart_qty_edits)):
            return
        edit = self._cart_qty_edits[index]
        total_lbl = self._cart_total_labels[index]
        self._on_cart_qty_edited(index, edit, total_lbl)
        if index + 1 < len(self._cart_qty_edits):
            self._focus_field(self._cart_qty_edits[index + 1])
        else:
            self._focus_field(self.discount_edit)

    def _move_qty_focus(self, index: int, delta: int) -> None:
        if not (0 <= index < len(self._cart_qty_edits)):
            return
        edit = self._cart_qty_edits[index]
        total_lbl = self._cart_total_labels[index]
        self._on_cart_qty_edited(index, edit, total_lbl)
        next_index = index + delta
        if 0 <= next_index < len(self._cart_qty_edits):
            self._focus_field(self._cart_qty_edits[next_index])

    def _on_cart_qty_edited(self, index: int, edit: QLineEdit, total_lbl: QLabel) -> None:
        if not (0 <= index < len(self._cart)):
            return
        text = edit.text().strip()
        try:
            val = Decimal(text)
            if val <= Decimal("0"):
                raise InvalidOperation
        except InvalidOperation:
            edit.setText(self._fmt_qty(self._cart[index]["quantity"]))
            return
        self._cart[index]["quantity"] = val.quantize(Decimal("0.01"))
        edit.setText(self._fmt_qty(self._cart[index]["quantity"]))
        line_total = self._cart[index]["unit_price"] * self._cart[index]["quantity"]
        total_lbl.setText(f"${line_total:.2f}")
        self._recalculate_totals()

    def _remove_from_cart(self, index: int) -> None:
        if 0 <= index < len(self._cart):
            self._cart.pop(index)
            self._refresh_cart_view()

    def _clear_cart(self) -> None:
        self._cart.clear()
        self._refresh_cart_view()

    def _recalculate_totals(self) -> None:
        subtotal = sum((item["unit_price"] * item["quantity"] for item in self._cart), Decimal("0.00"))
        self.subtotal_val_label.setText(f"${subtotal:.2f}")

        try:
            disc_val = Decimal(self.discount_edit.text().strip()) if self.discount_edit.text().strip() else Decimal("0.00")
        except InvalidOperation:
            disc_val = Decimal("0.00")

        try:
            tax_val = Decimal(self.tax_edit.text().strip()) if self.tax_edit.text().strip() else Decimal("0.00")
        except InvalidOperation:
            tax_val = Decimal("0.00")

        grand_total = subtotal - disc_val + tax_val
        if grand_total < Decimal("0.00"):
            grand_total = Decimal("0.00")

        self.grand_total_label.setText(f"${grand_total:.2f}")

        try:
            paid_val = Decimal(self.paid_edit.text().strip()) if self.paid_edit.text().strip() else Decimal("0.00")
        except InvalidOperation:
            paid_val = Decimal("0.00")

        if paid_val >= grand_total:
            change = paid_val - grand_total
            self.change_val_label.setText(f"Change: {change:.2f}")
            self.change_val_label.setStyleSheet("font-weight: 700; color: #16a34a;")
        else:
            due = grand_total - paid_val
            self.change_val_label.setText(f"Due: {due:.2f}")
            self.change_val_label.setStyleSheet("font-weight: 700; color: #dc2626;")

    def _complete_sale(self) -> None:
        if not self._cart:
            QMessageBox.warning(self, "Empty Cart", "Please add items to cart before completing sale.")
            return

        cust_id = self.customer_combo.currentData()

        try:
            disc_val = Decimal(self.discount_edit.text().strip()) if self.discount_edit.text().strip() else Decimal("0.00")
            tax_val = Decimal(self.tax_edit.text().strip()) if self.tax_edit.text().strip() else Decimal("0.00")
            paid_val = Decimal(self.paid_edit.text().strip()) if self.paid_edit.text().strip() else Decimal("0.00")
        except InvalidOperation:
            QMessageBox.warning(self, "Invalid Numbers", "Please verify discount, tax, or paid amount fields.")
            return

        payment_method = self.payment_method_combo.currentText()

        sale_items = [
            SaleItemInput(
                product_id=item["product_id"],
                product_name=item["product_name"],
                sku=item["sku"],
                barcode=item["barcode"],
                unit_price=item["unit_price"],
                cost_price=item["cost_price"],
                quantity=item["quantity"],
                discount_amount=item["discount_amount"],
            )
            for item in self._cart
        ]

        inp = SaleInput(
            customer_id=cust_id,
            items=sale_items,
            discount_amount=disc_val,
            tax_amount=tax_val,
            paid_amount=paid_val,
            payment_method=payment_method,
        )

        btn = self.complete_sale_button
        try:
            with saving_indicator(self, btn, message="Saving sale…", title="Checkout"):
                sale = self._sale_service.create_sale(inp)
        except SaleError as err:
            QMessageBox.critical(self, "Sale Failed", str(err))
            return

        # Show Receipt Dialog
        dlg = ReceiptDialog(sale, parent=self)
        dlg.exec()

        # Clear form & refresh
        self._clear_cart()
        self.discount_edit.setText("0.00")
        self.tax_edit.setText("0.00")
        self.paid_edit.setText("0.00")
        self.reload_data()

    # ── History & Search ──

    def _load_history(self) -> None:
        sales = self._sale_service.search_sales("")
        self._populate_history_table(sales)

    def _search_history(self) -> None:
        query = self.history_search_edit.text().strip()
        sales = self._sale_service.search_sales(query)
        self._populate_history_table(sales)

    def _clear_history_search(self) -> None:
        self.history_search_edit.clear()
        self._load_history()

    def _populate_history_table(self, sales: list[Sale]) -> None:
        self.history_table.setRowCount(0)
        for s in sales:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            inv_item = QTableWidgetItem(s.invoice_number)
            inv_item.setData(Qt.ItemDataRole.UserRole, s.id)
            self.history_table.setItem(row, 0, inv_item)

            date_str = s.sale_date.strftime("%Y-%m-%d %H:%M")
            self.history_table.setItem(row, 1, QTableWidgetItem(date_str))

            cust_name = s.customer.name if s.customer else "Walk-in Customer"
            self.history_table.setItem(row, 2, QTableWidgetItem(cust_name))

            self.history_table.setItem(row, 3, QTableWidgetItem(str(len(s.items))))
            self.history_table.setItem(row, 4, QTableWidgetItem(f"${s.total_amount:.2f}"))
            self.history_table.setItem(row, 5, QTableWidgetItem(f"${s.paid_amount:.2f}"))

            status_item = QTableWidgetItem(s.payment_status)
            if s.payment_status == "Paid":
                status_item.setForeground(Qt.GlobalColor.green)
            else:
                status_item.setForeground(Qt.GlobalColor.red)
            self.history_table.setItem(row, 6, status_item)

            self.history_table.setItem(row, 7, QTableWidgetItem(s.payment_method))

    def _view_selected_receipt(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select Sale", "Please select a sale transaction from the table.")
            return
        inv_item = self.history_table.item(row, 0)
        if inv_item:
            sale_id = inv_item.data(Qt.ItemDataRole.UserRole)
            sale = self._sale_service.get_sale(sale_id)
            if sale:
                dlg = ReceiptDialog(sale, parent=self)
                dlg.exec()

    def _void_selected_sale(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select Sale", "Please select a sale transaction to void.")
            return

        inv_item = self.history_table.item(row, 0)
        if not inv_item:
            return

        sale_id = inv_item.data(Qt.ItemDataRole.UserRole)
        sale = self._sale_service.get_sale(sale_id)
        if not sale:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Void Sale",
            f"Are you sure you want to void invoice {sale.invoice_number}?\nThis will revert customer balance adjustments.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self._sale_service.void_sale(sale_id):
                QMessageBox.information(self, "Sale Voided", f"Invoice {sale.invoice_number} has been voided.")
                self.reload_data()

    def _update_stats(self) -> None:
        stats = self._sale_service.get_summary_stats()
        self.stat_count_label.setText(f"Total Sales: {stats['total_count']}")
        self.stat_revenue_label.setText(f"Total Revenue: {stats['total_revenue']}")
        self.stat_unpaid_label.setText(f"Unpaid Receivables: {stats['total_unpaid']}")
