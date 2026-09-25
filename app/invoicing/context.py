"""Shared invoice formatting helpers and Sale → template context."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.infrastructure.database.models import Sale

STORE_NAME = "YOUR STORE NAME"


def money(value: Decimal | float | int | None) -> str:
    if value is None:
        return "0.00"
    return f"{Decimal(value):.2f}"


def rule(width: int, char: str = "-") -> str:
    return char * width


def center(text: str, width: int) -> str:
    text = text.strip()
    if len(text) >= width:
        return text[:width]
    return text.center(width)


def kv(label: str, value: str, width: int) -> str:
    label = label.rstrip()
    value = str(value).strip()
    gap = width - len(label) - len(value)
    if gap < 1:
        max_value = max(8, width - len(label) - 1)
        value = value[:max_value]
        gap = width - len(label) - len(value)
    return f"{label}{' ' * max(gap, 1)}{value}"


def wrap_name(name: str, width: int) -> list[str]:
    name = " ".join(str(name).split())
    if not name:
        return [""]
    lines: list[str] = []
    while name:
        if len(name) <= width:
            lines.append(name)
            break
        cut = name.rfind(" ", 0, width + 1)
        if cut <= 0:
            cut = width
        lines.append(name[:cut].rstrip())
        name = name[cut:].lstrip()
    return lines


def item_rows(
    name: str,
    qty: str,
    price: str,
    amount: str,
    *,
    item_w: int,
    qty_w: int,
    price_w: int,
    amount_w: int,
) -> list[str]:
    name_lines = wrap_name(name, item_w)
    rows: list[str] = []
    for i, line in enumerate(name_lines):
        if i == 0:
            rows.append(
                f"{line:<{item_w}}"
                f"{qty:>{qty_w}}"
                f"{price:>{price_w}}"
                f"{amount:>{amount_w}}"
            )
        else:
            rows.append(f"{'  ' + line:<{item_w}}")
    return rows


def build_invoice_context(sale: Sale, *, store_name: str = STORE_NAME) -> dict[str, Any]:
    """Normalize a Sale into template-friendly values."""
    customer_name = sale.customer.name if sale.customer else "Walk-in Customer"
    customer_phone = (
        sale.customer.phone
        if (sale.customer and sale.customer.phone)
        else "N/A"
    )
    items = [
        {
            "index": idx,
            "name": item.product_name,
            "quantity": money(item.quantity),
            "unit_price": money(item.unit_price),
            "line_total": money(item.line_total),
        }
        for idx, item in enumerate(sale.items, 1)
    ]
    discount = Decimal(sale.discount_amount or 0)
    tax = Decimal(sale.tax_amount or 0)
    change = Decimal(sale.change_amount or 0)
    return {
        "store_name": store_name,
        "invoice_number": sale.invoice_number,
        "sale_date": sale.sale_date.strftime("%d-%m-%Y %H:%M"),
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "payment_method": sale.payment_method,
        "payment_status": sale.payment_status,
        "items": items,
        "subtotal": money(sale.subtotal),
        "discount": money(discount) if discount > 0 else None,
        "tax": money(tax) if tax > 0 else None,
        "total": money(sale.total_amount),
        "paid": money(sale.paid_amount),
        "change": money(change) if change > 0 else None,
    }
