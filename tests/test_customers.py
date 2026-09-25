"""Customer domain service tests."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.customers.service import CustomerError, CustomerInput, CustomerService
from app.infrastructure.database.models import Base


@pytest.fixture
def service() -> Iterator[CustomerService]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield CustomerService(session)
    finally:
        session.close()
        engine.dispose()


def test_create_and_get_customer(service: CustomerService) -> None:
    inp = CustomerInput(
        name="  John Doe  ",
        phone=" 1234567890 ",
        email="john@example.com",
        city="New York",
        opening_balance=Decimal("150.00"),
        credit_limit=Decimal("1000.00"),
    )
    customer = service.create(inp)
    assert customer.id is not None
    assert customer.name == "John Doe"
    assert customer.phone == "1234567890"
    assert customer.email == "john@example.com"
    assert customer.city == "New York"
    assert customer.opening_balance == Decimal("150.00")
    assert customer.credit_limit == Decimal("1000.00")
    assert customer.is_active is True

    fetched = service.get(customer.id)
    assert fetched is not None
    assert fetched.name == "John Doe"


def test_create_customer_validation(service: CustomerService) -> None:
    with pytest.raises(CustomerError, match="name is required"):
        service.create(CustomerInput(name="   "))

    with pytest.raises(CustomerError, match="Invalid email address"):
        service.create(CustomerInput(name="Alice", email="invalid-email"))

    with pytest.raises(CustomerError, match="between 0% and 100%"):
        service.create(CustomerInput(name="Bob", discount_percent=Decimal("150.00")))


def test_customer_discount(service: CustomerService) -> None:
    c = service.create(CustomerInput(name="VIP Customer", discount_percent=Decimal("10.50")))
    assert c.discount_percent == Decimal("10.50")


def test_search_customers(service: CustomerService) -> None:
    service.create(CustomerInput(name="Alice Smith", phone="03001234567", city="Lahore"))
    service.create(CustomerInput(name="Bob Jones", phone="03009876543", city="Karachi"))
    service.create(CustomerInput(name="Charlie Brown", phone="03211112222", city="Lahore"))

    all_cust = service.search("")
    assert len(all_cust) == 3

    lahore_cust = service.search("Lahore")
    assert len(lahore_cust) == 2

    phone_cust = service.search("9876543")
    assert len(phone_cust) == 1
    assert phone_cust[0].name == "Bob Jones"


def test_update_customer(service: CustomerService) -> None:
    c = service.create(CustomerInput(name="Original Name", phone="111"))
    updated = service.update(
        c.id,
        CustomerInput(
            name="Updated Name",
            phone="222",
            email="updated@example.com",
            opening_balance=Decimal("500.00"),
        ),
    )
    assert updated.name == "Updated Name"
    assert updated.phone == "222"
    assert updated.email == "updated@example.com"
    assert updated.opening_balance == Decimal("500.00")


def test_delete_customer(service: CustomerService) -> None:
    c = service.create(CustomerInput(name="To Delete"))
    cid = c.id
    service.delete(cid)
    assert service.get(cid) is None

    with pytest.raises(CustomerError, match="not found"):
        service.delete(99999)


def test_summary_stats(service: CustomerService) -> None:
    service.create(CustomerInput(name="Customer 1", opening_balance=Decimal("100.00"), is_active=True))
    service.create(CustomerInput(name="Customer 2", opening_balance=Decimal("250.50"), is_active=False))

    stats = service.get_summary_stats()
    assert stats["total_count"] == 2
    assert stats["active_count"] == 1
    assert stats["total_balance"] == Decimal("350.50")


def test_customer_form_ui_interaction(service: CustomerService, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    from app.ui.customers.customer_form import CustomerForm

    form = CustomerForm(service)

    # Test initial tab count and state
    assert form._tabs.count() == 2
    assert form._tabs.tabText(0) == "Customer Listing"
    assert form._tabs.tabText(1) == "Add / Edit Customer"
    assert form.table.rowCount() == 0

    # Add customer via form
    form.name_edit.setText("Jane Doe")
    form.phone_edit.setText("030011122233")
    form.email_edit.setText("jane@example.com")
    form.city_edit.setText("Islamabad")
    form.address_edit.setText("Street 4, Sector G-8")
    form.balance_edit.setText("500.00")
    form.credit_limit_edit.setText("2000.00")
    form.discount_edit.setText("5.00")

    form._save()

    # Check that saving created a customer and updated the table
    assert form.table.rowCount() == 1
    assert form.table.item(0, 1).text() == "Jane Doe"
    assert form.table.item(0, 2).text() == "030011122233"
    assert form.table.item(0, 6).text() == "500.00"
    assert form.table.item(0, 8).text() == "5.00%"

    # Select row and open editor tab
    form.table.selectRow(0)
    form._open_selected_customer()
    assert form._tabs.currentIndex() == 1
    assert form.name_edit.text() == "Jane Doe"
    assert form.phone_edit.text() == "030011122233"

    # Edit customer
    form.name_edit.setText("Jane Smith")
    form.balance_edit.setText("750.00")
    form._save()

    assert form.table.rowCount() == 1
    assert form.table.item(0, 1).text() == "Jane Smith"
    assert form.table.item(0, 6).text() == "750.00"

    # Test searching
    form.search_edit.setText("Nonexistent")
    form._search()
    assert form.table.rowCount() == 0

    form._clear_search()
    assert form.table.rowCount() == 1

    # Delete customer
    form.table.selectRow(0)
    form._on_row_selected()
    form._delete()
    assert form.table.rowCount() == 0

