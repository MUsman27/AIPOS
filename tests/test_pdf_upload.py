"""Uploading a price list inserts new items and updates purchase prices."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database.models import Base, Product
from app.pdf_import.load import upsert_items
from app.pdf_import.parse import ParsedItem


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    opened = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield opened
    finally:
        opened.close()
        engine.dispose()


def test_existing_item_updates_purchase_price_and_keeps_sale_price(
    session: Session,
) -> None:
    upsert_items(
        session,
        "C.P",
        "old.pdf",
        [
            ParsedItem(
                description_en="AIR FILTER",
                purchase_price=Decimal("85.00"),
                description_ur="ائیر فلٹر",
                model="CD70-EURO2",
                item_code="36-0103-K0",
            )
        ],
    )
    product = session.scalar(select(Product).where(Product.sku == "36-0103-K0"))
    assert product is not None
    product.unit_price = Decimal("120.00")
    session.commit()

    inserted, updated = upsert_items(
        session,
        "C.P",
        "new.pdf",
        [
            ParsedItem(
                description_en="AIR FILTER",
                purchase_price=Decimal("90.00"),
                description_ur="ائیر فلٹر",
                model="CD70-EURO2",
                item_code="36-0103-K0",
            )
        ],
    )
    assert (inserted, updated) == (0, 1)
    session.refresh(product)
    assert product.cost_price == Decimal("90.00")
    assert product.unit_price == Decimal("120.00")


def test_new_item_in_an_upload_is_inserted(session: Session) -> None:
    inserted, updated = upsert_items(
        session,
        "RP Parts",
        "list.pdf",
        [
            ParsedItem(
                description_en="BACK LIGHT RP",
                purchase_price=Decimal("250.00"),
                model="CD70 CDI",
                item_code="02001003",
            )
        ],
    )
    assert (inserted, updated) == (1, 0)
    product = session.scalar(select(Product))
    assert product is not None
    assert product.cost_price == Decimal("250.00")
    assert product.unit_price is None


def test_single_column_list_leaves_english_blank_and_keeps_a_translation(
    session: Session,
) -> None:
    upsert_items(
        session,
        "MGP",
        "old.pdf",
        [
            ParsedItem(
                description_en="",
                purchase_price=Decimal("430.00"),
                description_ur="فٹ بار MATE BLACK",
                model="CD-70",
            )
        ],
    )
    product = session.scalar(select(Product))
    assert product is not None
    assert product.name is None
    assert product.description_ur == "فٹ بار MATE BLACK"

    product.name = "Foot bar"
    session.commit()

    inserted, updated = upsert_items(
        session,
        "MGP",
        "new.pdf",
        [
            ParsedItem(
                description_en="",
                purchase_price=Decimal("450.00"),
                description_ur="فٹ بار MATE BLACK",
                model="CD-70",
            )
        ],
    )
    assert (inserted, updated) == (0, 1)
    session.refresh(product)
    assert product.name == "Foot bar"
    assert product.cost_price == Decimal("450.00")
