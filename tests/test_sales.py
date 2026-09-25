"""Sale domain service unit tests."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.customers.service import CustomerInput, CustomerService
from app.domain.products.service import ProductInput, ProductService
from app.domain.sales.service import SaleError, SaleInput, SaleItemInput, SaleService
from app.infrastructure.database.models import Base


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sale_service(db_session: Session) -> SaleService:
    return SaleService(db_session)


@pytest.fixture
def customer_service(db_session: Session) -> CustomerService:
    return CustomerService(db_session)


@pytest.fixture
def product_service(db_session: Session) -> ProductService:
    return ProductService(db_session)


def test_create_sale_cash(
    sale_service: SaleService,
    product_service: ProductService,
) -> None:
    prod = product_service.create(
        ProductInput(name="Laptop Core i7", unit_price=Decimal("1200.00"), cost_price=Decimal("900.00"), sku="LAP-001")
    )

    inp = SaleInput(
        items=[
            SaleItemInput(
                product_id=prod.id,
                product_name=prod.name,
                sku=prod.sku,
                unit_price=Decimal("1200.00"),
                cost_price=Decimal("900.00"),
                quantity=Decimal("2.00"),
            )
        ],
        discount_amount=Decimal("100.00"),
        paid_amount=Decimal("2300.00"),
        payment_method="Cash",
    )

    sale = sale_service.create_sale(inp)
    assert sale.id is not None
    assert sale.invoice_number.startswith("INV-")
    assert sale.subtotal == Decimal("2400.00")
    assert sale.discount_amount == Decimal("100.00")
    assert sale.total_amount == Decimal("2300.00")
    assert sale.paid_amount == Decimal("2300.00")
    assert sale.change_amount == Decimal("0.00")
    assert sale.payment_status == "Paid"
    assert len(sale.items) == 1
    assert sale.items[0].line_total == Decimal("2400.00")


def test_create_sale_on_credit_updates_customer_balance(
    sale_service: SaleService,
    customer_service: CustomerService,
) -> None:
    cust = customer_service.create(CustomerInput(name="Acme Corp", opening_balance=Decimal("50.00")))

    inp = SaleInput(
        customer_id=cust.id,
        items=[
            SaleItemInput(
                product_name="Office Chair",
                unit_price=Decimal("150.00"),
                quantity=Decimal("2.00"),
            )
        ],
        paid_amount=Decimal("100.00"),
        payment_method="Credit",
    )

    sale = sale_service.create_sale(inp)
    assert sale.total_amount == Decimal("300.00")
    assert sale.paid_amount == Decimal("100.00")
    assert sale.payment_status == "Partial"

    # Balance should increase by unpaid portion: $300 - $100 = $200. $50 + $200 = $250.
    updated_cust = customer_service.get(cust.id)
    assert updated_cust is not None
    assert updated_cust.opening_balance == Decimal("250.00")


def test_create_sale_validation(sale_service: SaleService) -> None:
    with pytest.raises(SaleError, match="Cannot complete a sale with no items"):
        sale_service.create_sale(SaleInput(items=[]))

    with pytest.raises(SaleError, match="missing a product name"):
        sale_service.create_sale(
            SaleInput(items=[SaleItemInput(product_name=" ", unit_price=Decimal("10.00"))])
        )

    with pytest.raises(SaleError, match="greater than 0"):
        sale_service.create_sale(
            SaleInput(items=[SaleItemInput(product_name="Item A", unit_price=Decimal("10.00"), quantity=Decimal("0.00"))])
        )


def test_search_and_void_sale(
    sale_service: SaleService,
    customer_service: CustomerService,
) -> None:
    cust = customer_service.create(CustomerInput(name="Beta Logistics"))
    sale1 = sale_service.create_sale(
        SaleInput(
            customer_id=cust.id,
            items=[SaleItemInput(product_name="Truck Tire", unit_price=Decimal("200.00"), quantity=Decimal("1.00"))],
            paid_amount=Decimal("0.00"),
        )
    )

    results = sale_service.search_sales("Beta")
    assert len(results) == 1
    assert results[0].id == sale1.id

    assert cust.opening_balance == Decimal("200.00")

    success = sale_service.void_sale(sale1.id)
    assert success is True

    # Customer balance should be reverted
    refreshed_cust = customer_service.get(cust.id)
    assert refreshed_cust is not None
    assert refreshed_cust.opening_balance == Decimal("0.00")
