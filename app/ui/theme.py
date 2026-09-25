"""Light and dark theme palette for the POS app."""

LIGHT = {
  "bg": "#F5F7FB",
  "surface": "#FFFFFF",
  "surface_alt": "#F0F2F7",

  "border": "#D9DFEA",
  "border_focus": "#6366F1",

  "text": "#111827",
  "text_secondary": "#475569",
  "muted": "#7C8799",

  "sidebar": "#111827",
  "sidebar_hover": "#1E293B",
  "sidebar_selected": "#312E81",

  "primary": "#6366F1",
  "primary_hover": "#4F46E5",
  "primary_pressed": "#4338CA",
  "primary_text": "#FFFFFF",

  "accent": "#818CF8",
  "accent_light": "rgba(99, 102, 241, 0.12)",

  "success": "#16A36A",
  "success_hover": "#128456",

  "warning": "#D98A1E",
  "warning_hover": "#B87317",

  "danger": "#DC4444",
  "danger_hover": "#C23838",
  "danger_pressed": "#A92F2F",

  "table_selected": "#E0E7FF",
  "table_hover": "#F1F3FF",

  "header_bg": "#EEF1F7",
  "header_text": "#273449",

  "input_bg": "#FAFBFD",
  "input_shadow": "rgba(15, 23, 42, 0.04)",
  "card_shadow": "rgba(15, 23, 42, 0.06)",

  "section_accent": "#6366F1",

  "disabled_bg": "#E2E6ED",
  "disabled_text": "#9AA4B2"

}

DARK = {
"bg": "#0A1220",
    "surface": "#101E30",
    "surface_alt": "#162940",
    "border": "#263B55",
    "border_focus": "#6366F1",
    "text": "#E8F0FA",
    "text_secondary": "#A8BFDA",
    "muted": "#7A93B0",
    "sidebar": "#08101C",
    "sidebar_hover": "#0F1F35",
    "sidebar_selected": "#163052",
    "primary": "#6366F1",
    "primary_hover": "#818CF8",
    "primary_pressed": "#4F46E5",
    "primary_text": "#FFFFFF",
    "accent": "#818CF8",
    "accent_light": "rgba(129, 140, 248, 0.15)",
    "success": "#38C88A",
    "success_hover": "#2BB578",
    "warning": "#E5A84D",
    "danger": "#EF5B5B",
    "danger_hover": "#E04848",
    "danger_pressed": "#D03A3A",
    "table_selected": "#1A3A62",
    "table_hover": "#142E4E",
    "header_bg": "#142640",
    "header_text": "#D0E0F5",
    "input_bg": "#0D1B2E",
    "input_shadow": "rgba(0, 0, 0, 0.20)",
    "card_shadow": "rgba(0, 0, 0, 0.30)",
    "section_accent": "#6366F1",
    "disabled_bg": "#2A3A52",
    "disabled_text": "#556A82"
}


def build_stylesheet(theme: str) -> str:
    p = LIGHT if theme == "light" else DARK
    return f"""
/* ── Base ── */
QMainWindow, QWidget {{
    background: {p['bg']};
    color: {p['text']};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
}}

/* ── Sidebar ── */
QWidget#sidebar {{
    background: {p['sidebar']};
    border-right: 1px solid rgba(255,255,255,0.06);
}}

QWidget#sidebar QWidget,
QWidget#navSubContainer {{
    background: transparent;
}}

QStackedWidget {{
    background: transparent;
}}

QLabel {{
    background: transparent;
    color: {p['text']};
}}

/* ── Nav Toggle ── */
QPushButton#navToggle {{
    background: transparent;
    color: {p['text']};
    border: none;
    border-radius: 8px;
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
    padding: 0;
    margin: 0;
}}

QPushButton#navToggle:hover {{
    background: {p['sidebar_hover']};
}}

/* ── Nav Buttons ── */
QPushButton#navButton,
QPushButton#navGroupHeader {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0;
    margin: 0;
    min-width: 0;
    min-height: 38px;
    text-align: left;
}}

QPushButton#navButton:hover,
QPushButton#navGroupHeader:hover {{
    background: {p['sidebar_hover']};
}}

QPushButton#navButton:checked {{
    background: {p['sidebar_selected']};
    border-left: 3px solid {p['accent']};
}}

/* ── Sub Nav Buttons ── */
QPushButton#subNavButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0;
    margin: 0;
    min-width: 0;
    min-height: 38px;
    text-align: left;
}}

QPushButton#subNavButton:hover {{
    background: {p['sidebar_hover']};
}}

QPushButton#subNavButton:checked {{
    background: {p['sidebar_selected']};
    border-left: 3px solid {p['accent']};
}}

QWidget#sidebar QLabel#navIcon,
QWidget#sidebar QLabel#navLabel,
QWidget#sidebar QLabel#navArrow {{
    background: transparent;
    color: #dfeaf7;
    padding: 0;
    margin: 0;
}}

QPushButton#navButton:checked QLabel#navLabel {{
    color: #ffffff;
}}

QPushButton#subNavButton QLabel#navLabel {{
    color: #94a3b8;
    font-size: 13px;
}}

QPushButton#subNavButton:hover QLabel#navLabel {{
    color: #e2e8f0;
}}

QPushButton#subNavButton:checked QLabel#navLabel {{
    color: #ffffff;
    font-weight: 600;
}}

/* ── Page Title ── */
QLabel#pageTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {p['text']};
    margin-bottom: 4px;
    padding: 0;
}}

/* ── Search & Action Panels ── */
QWidget#searchPanel,
QWidget#actionBar {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 12px;
}}

/* ── Inputs ── */
QLineEdit {{
    background: {p['input_bg']};
    color: {p['text']};
    border: 1.5px solid {p['border']};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 26px;
    font-size: 13px;
    selection-background-color: {p['accent_light']};
    selection-color: {p['text']};
}}

QLineEdit::placeholder {{
    color: {p['muted']};
}}

QLineEdit#searchField {{
    min-height: 28px;
    font-size: 13px;
    padding: 5px 10px;
    border-radius: 8px;
}}

QLineEdit:focus {{
    border: 1.5px solid {p['border_focus']};
    background: {p['surface']};
}}

/* ── Spin Boxes ── */
QSpinBox, QDoubleSpinBox {{
    background: {p['input_bg']};
    color: {p['text']};
    border: 1.5px solid {p['border']};
    border-radius: 6px;
    padding: 4px 6px;
    min-height: 26px;
    font-size: 13px;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1.5px solid {p['border_focus']};
    background: {p['surface']};
}}

/* ── Form Labels ── */
QLabel#formLabel {{
    background: transparent;
    color: {p['text_secondary']};
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
    padding-bottom: 2px;
}}

QLabel#formSectionTitle {{
    background: transparent;
    color: {p['section_accent']};
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.4px;
    padding: 0;
    margin: 0;
}}

/* ── Checkbox ── */
QCheckBox {{
    spacing: 8px;
    color: {p['text']};
    font-size: 13.5px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1.5px solid {p['border']};
    background: {p['input_bg']};
}}

QCheckBox::indicator:checked {{
    background: {p['accent']};
    border-color: {p['accent']};
}}

QCheckBox::indicator:hover {{
    border-color: {p['accent']};
}}

/* ── Table ── */
QTableWidget {{
    background: {p['surface']};
    alternate-background-color: {p['surface_alt']};
    border: 1px solid {p['border']};
    border-radius: 12px;
    gridline-color: {p['border']};
    selection-background-color: {p['table_selected']};
    selection-color: {p['text']};
    color: {p['text']};
    font-size: 13px;
}}

QTableWidget#productTable {{
    outline: none;
}}

QTableWidget#productTable::item {{
    padding: 10px 8px;
    border-bottom: 1px solid {p['border']};
}}

QTableWidget#productTable::item:selected {{
    background: {p['table_selected']};
    color: {p['text']};
}}

QTableWidget#productTable::item:hover {{
    background: {p['table_hover']};
}}

QHeaderView::section {{
    background: {p['header_bg']};
    color: {p['header_text']};
    padding: 10px 8px;
    border: none;
    border-bottom: 2px solid {p['border']};
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 0.3px;
}}

/* ── Group Box ── */
QGroupBox {{
    background: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 12px;
    margin-top: 14px;
    padding: 20px 16px 16px 16px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 6px;
    color: {p['section_accent']};
    font-weight: 700;
    font-size: 14px;
}}

/* ── Buttons: Base ── */
QPushButton {{
    background: {p['primary']};
    color: {p['primary_text']};
    border: none;
    border-radius: 8px;
    padding: 5px 14px;
    min-width: 80px;
    min-height: 30px;
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.2px;
}}

QPushButton:hover {{
    background: {p['primary_hover']};
}}

QPushButton:pressed {{
    background: {p['primary_pressed']};
}}

/* ── Buttons: Primary (gradient) ── */
QPushButton#primaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {p['primary']}, stop:1 {p['accent']});
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: {p['primary_text']};
}}

QPushButton#primaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {p['primary_hover']}, stop:1 {p['accent']});
    border: 1px solid rgba(255, 255, 255, 0.20);
}}

QPushButton#primaryButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {p['primary_pressed']}, stop:1 {p['primary']});
}}

/* ── Buttons: Secondary ── */
QPushButton#secondaryButton {{
    background: {p['surface']};
    color: {p['text']};
    border: 1.5px solid {p['border']};
}}

QPushButton#secondaryButton:hover {{
    background: {p['surface_alt']};
    border-color: {p['accent']};
    color: {p['accent']};
}}

QPushButton#secondaryButton:pressed {{
    background: {p['accent_light']};
}}

/* ── Buttons: Success ── */
QPushButton#successButton {{
    background: {p['success']};
    color: #ffffff;
    border: none;
}}

QPushButton#successButton:hover {{
    background: {p['success_hover']};
}}

/* ── Buttons: Danger ── */
QPushButton#dangerButton {{
    background: {p['danger']};
    color: #ffffff;
    border: none;
}}

QPushButton#dangerButton:hover {{
    background: {p['danger_hover']};
}}

QPushButton#dangerButton:pressed {{
    background: {p['danger_pressed']};
}}

/* ── Buttons: Disabled ── */
QPushButton:disabled {{
    background: {p['disabled_bg']};
    color: {p['disabled_text']};
    border: none;
}}

/* ── Theme Toggle ── */
QPushButton#navToggle,
QPushButton#themeToggle {{
    background: transparent;
    color: {p['text']};
    border: none;
    border-radius: 8px;
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
    padding: 0;
    margin: 0;
}}

QPushButton#navToggle:hover,
QPushButton#themeToggle:hover {{
    background: {p['sidebar_hover']};
}}

/* ── ComboBox ── */
QComboBox {{
    background: {p['input_bg']};
    color: {p['text']};
    border: 1.5px solid {p['border']};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 26px;
    font-size: 13px;
}}

QComboBox:focus {{
    border: 1.5px solid {p['border_focus']};
    background: {p['surface']};
}}

QComboBox#productManufacturer {{
    font-size: 13px;
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}

QComboBox QAbstractItemView {{
    background: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    selection-background-color: {p['table_selected']};
    selection-color: {p['text']};
    padding: 4px;
    outline: none;
}}

/* ── Scrollbar ── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {p['border']};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p['muted']};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {p['border']};
    border-radius: 4px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {p['muted']};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Separator lines ── */
QFrame#formSeparator {{
    background: {p['border']};
    max-height: 1px;
    min-height: 1px;
    margin: 4px 0;
}}

/* ── Form Card ── */
QWidget#formCard {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 10px;
}}

QScrollArea#cartScroll {{
    background: transparent;
    border: none;
}}

QWidget#cartListHost {{
    background: transparent;
}}

QWidget#cartListHeader {{
    background: {p['header_bg']};
    border: 1px solid {p['border']};
    border-radius: 6px;
}}

QWidget#cartItemRow {{
    background: {p['surface_alt']};
    border: 1px solid {p['border']};
    border-radius: 8px;
}}

/* ── Tab Widget ── */
QTabWidget::pane {{
    background: {p['bg']};
    border: 1px solid {p['border']};
    border-top: none;
    border-radius: 0 0 10px 10px;
}}

QTabBar::tab {{
    background: {p['surface_alt']};
    color: {p['muted']};
    border: 1px solid {p['border']};
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 8px 20px;
    margin-right: 2px;
    font-weight: 600;
    font-size: 13px;
}}

QTabBar::tab:selected {{
    background: {p['bg']};
    color: {p['accent']};
    border-bottom: 2px solid {p['accent']};
}}

QTabBar::tab:hover:!selected {{
    background: {p['surface']};
    color: {p['text']};
}}

/* ── Progress Dialog ── */
QProgressDialog {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 12px;
}}

/* ── Message Box ── */
QMessageBox {{
    background: {p['surface']};
}}

QMessageBox QLabel {{
    color: {p['text']};
    font-size: 13px;
}}
"""
