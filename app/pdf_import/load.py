"""Upsert parsed price-list rows into manufacturers and products."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import Manufacturer, Product
from app.pdf_import.parse import ParsedItem
from app.pdf_import.read import read_price_list


def import_file(session: Session, path: Path) -> tuple[str, int, int]:
    """Import one PDF. Existing items keep their sale price and get a new purchase price."""
    if path.suffix.lower() != ".pdf":
        raise ValueError("Choose a PDF file.")
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    manufacturer_name, items = read_price_list(path)
    if not items:
        raise ValueError(f"No items were found in {path.name}.")
    inserted, updated = upsert_items(session, manufacturer_name, path.name, items)
    return manufacturer_name, inserted, updated


def import_folder(session: Session, folder: Path) -> list[tuple[str, int, int]]:
    """Import every PDF in folder. Returns (manufacturer, inserted, updated)."""
    summaries: list[tuple[str, int, int]] = []
    paths = sorted(folder.glob("*.pdf"))
    if not paths:
        raise FileNotFoundError(f"No PDF files in {folder}")
    for path in paths:
        print(f"Reading {path.name}", flush=True)
        manufacturer_name, items = read_price_list(path)
        inserted, updated = upsert_items(
            session,
            manufacturer_name,
            path.name,
            items,
        )
        print(
            f"  {manufacturer_name}: {inserted} new, {updated} updated",
            flush=True,
        )
        summaries.append((manufacturer_name, inserted, updated))
    return summaries


def upsert_items(
    session: Session,
    manufacturer_name: str,
    source_file: str,
    items: list[ParsedItem],
) -> tuple[int, int]:
    manufacturer = session.scalar(
        select(Manufacturer).where(Manufacturer.name == manufacturer_name)
    )
    if manufacturer is None:
        manufacturer = Manufacturer(name=manufacturer_name, source_file=source_file)
        session.add(manufacturer)
        session.flush()
    else:
        manufacturer.source_file = source_file

    inserted = 0
    updated = 0
    for item in items:
        existing = _find_existing(session, manufacturer.id, item)
        if existing is None:
            session.add(
                Product(
                    manufacturer=manufacturer,
                    sku=item.item_code,
                    name=item.description_en or None,
                    description_ur=item.description_ur,
                    model=item.model,
                    cost_price=item.purchase_price,
                    unit_price=None,
                    is_active=True,
                )
            )
            inserted += 1
        else:
            if item.description_en:
                existing.name = item.description_en
            elif _english_is_untranslated(existing, item):
                existing.name = None
            existing.description_ur = item.description_ur
            existing.model = item.model
            existing.cost_price = item.purchase_price
            if item.item_code and existing.sku is None:
                existing.sku = item.item_code
            updated += 1
    session.commit()
    return inserted, updated


def _find_existing(
    session: Session, manufacturer_id: int, item: ParsedItem
) -> Product | None:
    if item.item_code:
        return session.scalar(
            select(Product).where(
                Product.manufacturer_id == manufacturer_id,
                Product.sku == item.item_code,
            )
        )
    statement = select(Product).where(Product.manufacturer_id == manufacturer_id)
    if item.description_en:
        statement = statement.where(Product.name == item.description_en)
    else:
        statement = statement.where(
            or_(
                Product.description_ur == item.description_ur,
                Product.name == item.description_ur,
            )
        )
    if item.model is None:
        statement = statement.where(Product.model.is_(None))
    else:
        statement = statement.where(Product.model == item.model)
    return session.scalars(statement).first()


def _english_is_untranslated(product: Product, item: ParsedItem) -> bool:
    """True when English is empty or only a copy of the single description cell."""
    current = (product.name or "").strip()
    previous_urdu = (product.description_ur or "").strip()
    incoming_urdu = (item.description_ur or "").strip()
    return not current or current in {previous_urdu, incoming_urdu}
