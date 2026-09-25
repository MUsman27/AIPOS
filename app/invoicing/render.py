"""Jinja2 environment and invoice render entry points."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.infrastructure.database.models import Sale
from app.invoicing.context import (
    build_invoice_context,
    center,
    item_rows,
    kv,
    money,
    rule,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_THERMAL_SPEC = {
    "width": 38,
    "item_w": 19,
    "qty_w": 4,
    "price_w": 7,
    "amount_w": 8,
}


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html", "htm", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals.update(
        {
            "rule": rule,
            "center": center,
            "kv": kv,
            "item_rows": item_rows,
            "money": money,
        }
    )
    return env


def render_thermal_text(sale: Sale, *, store_name: str | None = None) -> str:
    ctx = build_invoice_context(
        sale,
        store_name=store_name or "YOUR STORE NAME",
    )
    ctx["spec"] = _THERMAL_SPEC
    text = _env().get_template("thermal.txt").render(**ctx)
    return text.rstrip() + "\n"


def render_a4_html(sale: Sale, *, store_name: str | None = None) -> str:
    ctx = build_invoice_context(
        sale,
        store_name=store_name or "YOUR STORE NAME",
    )
    return _env().get_template("a4.html").render(**ctx)
