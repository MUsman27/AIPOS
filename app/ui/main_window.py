"""Application shell with a collapsible sidebar."""

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain.customers.service import CustomerService
from app.domain.products.service import ProductService
from app.domain.sales.service import SaleService
from app.infrastructure.database.session import get_session
from app.ui.customers.customer_form import CustomerForm
from app.ui.products.product_form import ProductForm
from app.ui.products.products_setting_page import ProductsSettingPage
from app.ui.sales.sale_form import SaleForm
from app.ui.theme import build_stylesheet


_ICON_SLOT = 40
_ICON_PX = 20
_SIDE_MARGIN = 12
_EXPANDED_WIDTH = 216
_COLLAPSED_WIDTH = _SIDE_MARGIN * 2 + _ICON_SLOT
_ICONS = Path(__file__).resolve().parents[2] / "resources" / "icons"


def _icon(name: str) -> QIcon:
    return QIcon(str(_ICONS / f"{name}.svg"))


def _scaled_pixmap(icon: QIcon, logical_px: int, widget: QWidget) -> QPixmap:
    ratio = widget.devicePixelRatioF()
    pixels = max(1, round(logical_px * ratio))
    pixmap = icon.pixmap(QSize(pixels, pixels))
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


class NavLink(QPushButton):
    """Icon in a fixed column, with the label beside it. Supports sub-link styling."""

    def __init__(self, icon: QIcon, title: str, is_sub: bool = False) -> None:
        super().__init__()
        self._source_icon = icon
        self._is_sub = is_sub
        self.setObjectName("subNavButton" if is_sub else "navButton")
        self.setCheckable(True)
        self.setToolTip(title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(0)
        self.setFixedHeight(34 if is_sub else _ICON_SLOT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFlat(True)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("navIcon")
        icon_slot = 32 if is_sub else _ICON_SLOT
        self._icon_label.setFixedSize(icon_slot, 34 if is_sub else _ICON_SLOT)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._text_label = QLabel(title)
        self._text_label.setObjectName("navLabel")
        self._text_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._text_label.setMinimumWidth(0)
        self._text_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        self._row = QHBoxLayout(self)
        left_margin = 16 if is_sub else 0
        self._row.setContentsMargins(left_margin, 0, 8, 0)
        self._row.setSpacing(0)
        self._row.addWidget(self._icon_label)
        self._row.addWidget(self._text_label, stretch=1)
        self._apply_pixmap()

    def showEvent(self, event: QShowEvent) -> None:
        self._apply_pixmap()
        super().showEvent(event)

    def set_collapsed(self, collapsed: bool) -> None:
        self._text_label.setVisible(not collapsed)
        if self._is_sub:
            margin = 0 if collapsed else 16
            self._row.setContentsMargins(margin, 0, 8, 0)

    def _apply_pixmap(self) -> None:
        px_size = 16 if self._is_sub else _ICON_PX
        self._icon_label.setPixmap(_scaled_pixmap(self._source_icon, px_size, self))


class NavGroupHeader(QPushButton):
    """Parent group item in sidebar that expands/collapses sub-items."""

    def __init__(self, icon: QIcon, title: str) -> None:
        super().__init__()
        self._source_icon = icon
        self.setObjectName("navGroupHeader")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(0)
        self.setFixedHeight(_ICON_SLOT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFlat(True)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("navIcon")
        self._icon_label.setFixedSize(_ICON_SLOT, _ICON_SLOT)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._text_label = QLabel(title)
        self._text_label.setObjectName("navLabel")
        self._text_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._text_label.setMinimumWidth(0)
        self._text_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        self._arrow_label = QLabel()
        self._arrow_label.setObjectName("navArrow")
        self._arrow_label.setFixedSize(20, _ICON_SLOT)
        self._arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 8, 0)
        row.setSpacing(0)
        row.addWidget(self._icon_label)
        row.addWidget(self._text_label, stretch=1)
        row.addWidget(self._arrow_label)

        self._expanded = True
        self._update_arrow()
        self._apply_pixmap()

    def showEvent(self, event: QShowEvent) -> None:
        self._apply_pixmap()
        super().showEvent(event)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._update_arrow()

    def is_expanded(self) -> bool:
        return self._expanded

    def set_collapsed(self, collapsed: bool) -> None:
        self._text_label.setVisible(not collapsed)
        self._arrow_label.setVisible(not collapsed)

    def _update_arrow(self) -> None:
        arrow_icon = _icon("chevron-down" if self._expanded else "chevron-right")
        self._arrow_label.setPixmap(_scaled_pixmap(arrow_icon, 12, self))

    def _apply_pixmap(self) -> None:
        self._icon_label.setPixmap(_scaled_pixmap(self._source_icon, _ICON_PX, self))
        self._update_arrow()


class PlaceholderPage(QWidget):
    def __init__(self, title: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(f"{title} is not built yet.")
        label.setObjectName("pageTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("POS")
        self.resize(1100, 700)
        self._collapsed = False
        self._theme = "light"
        self._width_anim: QVariantAnimation | None = None

        self._session = get_session()
        self._service = ProductService(self._session)
        self._customer_service = CustomerService(self._session)
        self._sale_service = SaleService(self._session)

        self._sidebar = QWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(_EXPANDED_WIDTH)

        self.toggle_button = QPushButton()
        self.toggle_button.setObjectName("navToggle")
        self.toggle_button.setIcon(_icon("chevron-left"))
        self.toggle_button.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self.toggle_button.setToolTip("Collapse navigation")
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setMinimumWidth(0)
        self.toggle_button.setFixedSize(_ICON_SLOT, _ICON_SLOT)
        self.toggle_button.clicked.connect(self._toggle_nav)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeToggle")
        self.theme_button.setIcon(_icon("moon"))
        self.theme_button.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self.theme_button.setToolTip("Switch to dark mode")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setFixedSize(_ICON_SLOT, _ICON_SLOT)
        self.theme_button.clicked.connect(self._toggle_theme)

        self._header_layout = QHBoxLayout()
        self._header_layout.setContentsMargins(0, 0, 0, 8)
        self._header_layout.addWidget(self.toggle_button, 0, Qt.AlignmentFlag.AlignLeft)
        self._header_layout.addStretch(1)

        self._nav_items: list[NavLink | NavGroupHeader] = []
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        nav_layout = QVBoxLayout()
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(2)

        self.stack = QStackedWidget()

        # Multi-level Nav Group: Products
        prod_header = NavGroupHeader(_icon("products"), "Products")
        self._nav_items.append(prod_header)

        sub_container = QWidget()
        sub_container.setObjectName("navSubContainer")
        sub_layout = QVBoxLayout(sub_container)
        sub_layout.setContentsMargins(0, 0, 0, 0)
        sub_layout.setSpacing(2)

        prod_sub_pages = [
            ("Products Form", "products", ProductForm(self._service)),
            ("Products Setting", "translate", ProductsSettingPage(self._service)),
        ]

        sub_buttons: list[NavLink] = []
        for title, icon_name, page in prod_sub_pages:
            idx = self.stack.addWidget(page)
            btn = NavLink(_icon(icon_name), title, is_sub=True)
            self._nav_group.addButton(btn, idx)
            self._nav_items.append(btn)
            sub_buttons.append(btn)
            sub_layout.addWidget(btn)

        def _toggle_products() -> None:
            exp = not prod_header.is_expanded()
            prod_header.set_expanded(exp)
            sub_container.setVisible(exp)

        prod_header.clicked.connect(_toggle_products)

        nav_layout.addWidget(prod_header)
        nav_layout.addWidget(sub_container)

        # Top-level single nav items
        top_pages = [
            (
                "Sales",
                "sales",
                SaleForm(
                    self._sale_service, self._service, self._customer_service
                ),
            ),
            ("Inventory", "inventory", PlaceholderPage("Inventory")),
            ("Purchases", "purchases", PlaceholderPage("Purchases")),
            ("Customers", "customers", CustomerForm(self._customer_service)),
            ("Reports", "reports", PlaceholderPage("Reports")),
        ]

        for title, icon_name, page in top_pages:
            idx = self.stack.addWidget(page)
            btn = NavLink(_icon(icon_name), title, is_sub=False)
            self._nav_group.addButton(btn, idx)
            self._nav_items.append(btn)
            nav_layout.addWidget(btn)

        nav_layout.addStretch(1)

        self._nav_group.idClicked.connect(self.stack.setCurrentIndex)
        sub_buttons[0].setChecked(True)
        self.stack.setCurrentIndex(0)

        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(_SIDE_MARGIN, _SIDE_MARGIN, _SIDE_MARGIN, _SIDE_MARGIN)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addLayout(self._header_layout)
        sidebar_layout.addLayout(nav_layout, stretch=1)
        sidebar_layout.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignLeft)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar)
        layout.addWidget(self.stack, stretch=1)
        self.setCentralWidget(root)

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        if theme == "dark":
            self.theme_button.setIcon(_icon("sun"))
            self.theme_button.setToolTip("Switch to light mode")
        else:
            self.theme_button.setIcon(_icon("moon"))
            self.theme_button.setToolTip("Switch to dark mode")
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(theme))

    def _toggle_theme(self) -> None:
        next_theme = "dark" if self._theme == "light" else "light"
        self.set_theme(next_theme)

    def _toggle_nav(self) -> None:
        self._set_nav_collapsed(not self._collapsed, animate=True)

    def _set_nav_collapsed(self, collapsed: bool, *, animate: bool) -> None:
        self._collapsed = collapsed
        for item in self._nav_items:
            item.set_collapsed(collapsed)
        self.toggle_button.setIcon(
            _icon("chevron-right" if collapsed else "chevron-left")
        )
        self.toggle_button.setToolTip(
            "Expand navigation" if collapsed else "Collapse navigation"
        )
        target = _COLLAPSED_WIDTH if collapsed else _EXPANDED_WIDTH
        if animate:
            self._animate_sidebar(target)
            return
        self._sidebar.setFixedWidth(target)

    def _animate_sidebar(self, width: int) -> None:
        if self._width_anim is not None:
            self._width_anim.stop()
        animation = QVariantAnimation(self)
        animation.setStartValue(self._sidebar.width())
        animation.setEndValue(width)
        animation.setDuration(180)
        animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        animation.valueChanged.connect(
            lambda value: self._sidebar.setFixedWidth(int(value))
        )
        animation.start()
        self._width_anim = animation

    def closeEvent(self, event: QCloseEvent) -> None:
        self._session.close()
        super().closeEvent(event)
