"""Product catalog service tests."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.products.service import ProductError, ProductInput, ProductService
from app.infrastructure.database.models import Base


@pytest.fixture
def service() -> Iterator[ProductService]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield ProductService(session)
    finally:
        session.close()
        engine.dispose()


def product_input(
    *,
    name: str = "Milk",
    sku: str | None = "SKU-1",
    barcode: str | None = "111222333",
    unit_price: Decimal | None = Decimal("2.50"),
    cost_price: Decimal | None = Decimal("1.20"),
    is_active: bool = True,
    description_ur: str | None = None,
    model: str | None = None,
    manufacturer_name: str | None = None,
) -> ProductInput:
    return ProductInput(
        name=name,
        sku=sku,
        barcode=barcode,
        unit_price=unit_price,
        cost_price=cost_price,
        is_active=is_active,
        description_ur=description_ur,
        model=model,
        manufacturer_name=manufacturer_name,
    )


def test_create_product_and_lookup_barcode(service: ProductService) -> None:
    created = service.create(
        product_input(sku="  SKU-1  ", barcode="  111222333\n")
    )
    assert created.id is not None
    assert created.name == "Milk"
    assert created.sku == "SKU-1"
    assert created.barcode == "111222333"
    assert created.unit_price == Decimal("2.50")
    assert created.is_active is True

    found = service.get_by_barcode("  111222333\n")
    assert found is not None
    assert found.id == created.id


def test_update_product(service: ProductService) -> None:
    created = service.create(product_input())
    updated = service.update(
        created.id,
        product_input(name="Whole Milk", unit_price=Decimal("3.00"), barcode="999"),
    )
    assert updated.name == "Whole Milk"
    assert updated.unit_price == Decimal("3.00")
    assert updated.barcode == "999"
    assert service.get_by_barcode("111222333") is None
    assert service.get(created.id) is not None


def test_search_matches_name_sku_or_barcode(service: ProductService) -> None:
    service.create(product_input(name="Milk", sku="DAIRY-1", barcode="111"))
    service.create(product_input(name="Bread", sku="BAKE-1", barcode="222"))

    assert [item.name for item in service.search("mil")] == ["Milk"]
    assert [item.name for item in service.search("bake")] == ["Bread"]
    assert [item.name for item in service.search("222")] == ["Bread"]
    assert {item.name for item in service.search("")} == {"Milk", "Bread"}


def test_duplicate_barcode_is_rejected(service: ProductService) -> None:
    service.create(product_input())
    with pytest.raises(ProductError, match="Barcode"):
        service.create(product_input(name="Other", sku="SKU-2", barcode="111222333"))


def test_duplicate_sku_is_rejected(service: ProductService) -> None:
    service.create(product_input())
    with pytest.raises(ProductError, match="SKU"):
        service.create(product_input(name="Other", sku="SKU-1", barcode="444"))


def test_update_rejects_duplicate_barcode(service: ProductService) -> None:
    first = service.create(product_input())
    second = service.create(product_input(name="Bread", sku="SKU-2", barcode="444"))
    with pytest.raises(ProductError, match="Barcode"):
        service.update(
            second.id,
            product_input(name="Bread", sku="SKU-2", barcode=first.barcode),
        )


def test_blank_barcode_and_sku_can_repeat(service: ProductService) -> None:
    service.create(product_input(name="Loose Apples", sku=None, barcode="  "))
    service.create(product_input(name="Bulk Rice", sku="", barcode=None))
    rows = service.search("")
    assert [row.name for row in rows] == ["Bulk Rice", "Loose Apples"]
    assert all(row.sku is None and row.barcode is None for row in rows)


def test_name_and_price_are_validated(service: ProductService) -> None:
    with pytest.raises(ProductError, match="English description"):
        service.create(product_input(name="  "))
    with pytest.raises(ProductError, match="Sale price"):
        service.create(product_input(unit_price=Decimal("-1")))
    with pytest.raises(ProductError, match="Purchase price"):
        service.create(product_input(cost_price=Decimal("-0.01")))


def test_sale_price_can_be_empty(service: ProductService) -> None:
    created = service.create(
        product_input(
            name="Air Filter",
            unit_price=None,
            cost_price=Decimal("85"),
            description_ur="ایئر فلٹر",
            model="CD70",
            manufacturer_name="C.P",
        )
    )
    assert created.unit_price is None
    assert created.cost_price == Decimal("85.00")
    assert created.description_ur == "ایئر فلٹر"
    assert created.model == "CD70"
    assert created.manufacturer is not None
    assert created.manufacturer.name == "C.P"


def test_same_sku_is_allowed_for_different_manufacturers(service: ProductService) -> None:
    service.create(
        product_input(name="Filter", sku="36-0103-K0", manufacturer_name="C.P")
    )
    other = service.create(
        product_input(
            name="Filter",
            sku="36-0103-K0",
            barcode="555",
            manufacturer_name="RP Parts",
        )
    )
    assert other.sku == "36-0103-K0"
    assert other.manufacturer is not None
    assert other.manufacturer.name == "RP Parts"


def test_search_matches_urdu_model_and_manufacturer(service: ProductService) -> None:
    service.create(
        product_input(
            name="Air Filter",
            sku="36-0103-K0",
            barcode="777",
            description_ur="ایئر فلٹر",
            model="CD70-EURO2",
            manufacturer_name="C.P",
        )
    )
    assert [item.name for item in service.search("فلٹر")] == ["Air Filter"]
    assert [item.name for item in service.search("euro2")] == ["Air Filter"]
    assert [item.name for item in service.search("c.p")] == ["Air Filter"]


def test_translate_missing_names_uses_urdu_description(service: ProductService) -> None:
    created = service.create(
        product_input(
            name="",
            description_ur="ایئر فلٹر",
            sku="T-1",
            barcode="111222333444",
        )
    )
    service.update(
        created.id,
        product_input(
            name="",
            description_ur="ایئر فلٹر",
            sku="T-1",
            barcode="111222333444",
        ),
    )

    updated = service.translate_missing_names(
        translator=lambda text: "Air Filter" if text == "ایئر فلٹر" else text
    )

    assert updated == 1
    assert service.get(created.id).name == "Air Filter"


def test_translate_selected_products_only_updates_selected_rows(service: ProductService) -> None:
    first = service.create(
        product_input(
            name="",
            description_ur="ایئر فلٹر",
            sku="T-1",
            barcode="111222333444",
        )
    )
    second = service.create(
        product_input(
            name="",
            description_ur="بیٹری",
            sku="T-2",
            barcode="111222333445",
        )
    )

    updated = service.translate_selected_missing_names(
        [first.id, second.id],
        translator=lambda text: "Air Filter" if text == "ایئر فلٹر" else "Battery",
    )

    assert updated == 2
    assert service.get(first.id).name == "Air Filter"
    assert service.get(second.id).name == "Battery"


def test_delete_product(service: ProductService) -> None:
    created = service.create(product_input())
    service.delete(created.id)
    assert service.get(created.id) is None
    assert service.search("Milk") == []
    with pytest.raises(ProductError, match="not found"):
        service.delete(created.id)


def test_product_form_tab_change_clears_inputs(service: ProductService) -> None:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from app.ui.products.product_form import ProductForm

    prod = service.create(product_input(name="Spark Plug", sku="SP-100"))
    form = ProductForm(service)

    # Select product in table
    form.table.selectRow(0)
    assert form._product_id == prod.id
    assert form.name_edit.text() == "Spark Plug"

    # Open product (simulates double click / enter)
    form._open_selected_product()
    assert form._tabs.currentIndex() == 1
    assert form._product_id == prod.id
    assert form.name_edit.text() == "Spark Plug"

    # Switch tab back to Listing (index 0)
    form._tabs.setCurrentIndex(0)
    assert form._product_id is None
    assert form.name_edit.text() == ""
    assert form.sku_edit.text() == ""
    assert form.delete_button.isEnabled() is False


def test_batch_update_sale_prices(service: ProductService) -> None:
    p1 = service.create(
        product_input(name="P1", sku="SKU-BATCH-1", barcode="1111", unit_price=Decimal("10.00"), cost_price=Decimal("8.00"))
    )
    p2 = service.create(
        product_input(name="P2", sku="SKU-BATCH-2", barcode="2222", unit_price=Decimal("20.00"), cost_price=Decimal("15.00"))
    )

    updated_count = service.update_sale_prices([
        (p1.id, Decimal("9.20")),
        (p2.id, Decimal("17.25")),
    ])

    assert updated_count == 2
    assert service.get(p1.id).unit_price == Decimal("9.20")
    assert service.get(p2.id).unit_price == Decimal("17.25")


def test_products_setting_page_tabs_and_calculation(
    service: ProductService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    from app.ui.products.products_setting_page import ProductsSettingPage

    p1 = service.create(product_input(name="Filter", unit_price=Decimal("100"), cost_price=Decimal("80")))
    page = ProductsSettingPage(service)

    # Verify tabs exist
    assert page.tabs.count() == 2
    assert page.tabs.tabText(0) == "Translation"
    assert page.tabs.tabText(1) == "Price Calculation"

    # Test percentage markup calculation (e.g. 20%)
    page.percent_edit.setText("20")
    page._apply_percentage()

    # Verify updated sale price in price_table cell (80 * 1.20 = 96.00)
    sale_item = page.price_table.item(0, 5)
    assert sale_item is not None
    assert sale_item.text() == "96.00"

    # Save prices and verify in database
    page._save_prices()
    assert service.get(p1.id).unit_price == Decimal("96.00")


