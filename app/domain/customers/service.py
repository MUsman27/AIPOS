"""Customer service for managing customer records."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import Customer


class CustomerError(Exception):
    """Domain error raised during customer operations."""


@dataclass
class CustomerInput:
    """Input payload for creating or updating a customer."""

    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    opening_balance: Decimal | None = Decimal("0.00")
    credit_limit: Decimal | None = None
    discount_percent: Decimal | None = Decimal("0.00")
    notes: str | None = None
    is_active: bool = True


class CustomerService:
    """Business logic for managing customer records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, customer_id: int) -> Customer | None:
        """Fetch customer by primary key."""
        return self._session.get(Customer, customer_id)

    def get_by_phone(self, phone: str) -> Customer | None:
        """Find a customer by exact phone number match."""
        cleaned = phone.strip()
        if not cleaned:
            return None
        stmt = select(Customer).where(Customer.phone == cleaned)
        return self._session.scalar(stmt)

    def search(self, query: str = "") -> list[Customer]:
        """Search customers by name, phone, email, city, or address."""
        cleaned = query.strip()
        stmt = select(Customer)
        if cleaned:
            pattern = f"%{cleaned}%"
            stmt = stmt.where(
                or_(
                    Customer.name.ilike(pattern),
                    Customer.phone.ilike(pattern),
                    Customer.email.ilike(pattern),
                    Customer.city.ilike(pattern),
                    Customer.address.ilike(pattern),
                )
            )
        stmt = stmt.order_by(Customer.name.asc())
        return list(self._session.scalars(stmt).all())

    def create(self, data: CustomerInput) -> Customer:
        """Create a new customer."""
        validated = self._validate_and_clean(data)
        customer = Customer(
            name=validated.name,
            phone=validated.phone,
            email=validated.email,
            address=validated.address,
            city=validated.city,
            opening_balance=validated.opening_balance or Decimal("0.00"),
            credit_limit=validated.credit_limit,
            discount_percent=validated.discount_percent or Decimal("0.00"),
            notes=validated.notes,
            is_active=validated.is_active,
        )
        self._session.add(customer)
        self._session.commit()
        self._session.refresh(customer)
        return customer

    def update(self, customer_id: int, data: CustomerInput) -> Customer:
        """Update an existing customer."""
        customer = self.get(customer_id)
        if customer is None:
            raise CustomerError(f"Customer with ID {customer_id} not found.")

        validated = self._validate_and_clean(data)
        customer.name = validated.name
        customer.phone = validated.phone
        customer.email = validated.email
        customer.address = validated.address
        customer.city = validated.city
        customer.opening_balance = validated.opening_balance or Decimal("0.00")
        customer.credit_limit = validated.credit_limit
        customer.discount_percent = validated.discount_percent or Decimal("0.00")
        customer.notes = validated.notes
        customer.is_active = validated.is_active

        self._session.commit()
        self._session.refresh(customer)
        return customer

    def delete(self, customer_id: int) -> None:
        """Delete a customer record."""
        customer = self.get(customer_id)
        if customer is None:
            raise CustomerError(f"Customer with ID {customer_id} not found.")
        self._session.delete(customer)
        self._session.commit()

    def get_summary_stats(self) -> dict[str, int | Decimal]:
        """Compute aggregate summary metrics for customers."""
        customers = self.search("")
        total_count = len(customers)
        active_count = sum(1 for c in customers if c.is_active)
        total_balance = sum((c.opening_balance for c in customers if c.opening_balance), Decimal("0.00"))
        return {
            "total_count": total_count,
            "active_count": active_count,
            "total_balance": total_balance,
        }

    def _validate_and_clean(self, data: CustomerInput) -> CustomerInput:
        name = data.name.strip()
        if not name:
            raise CustomerError("Customer name is required.")

        phone = data.phone.strip() if data.phone else None
        if phone == "":
            phone = None

        email = data.email.strip() if data.email else None
        if email == "":
            email = None
        elif email and "@" not in email:
            raise CustomerError("Invalid email address format.")

        address = data.address.strip() if data.address else None
        if address == "":
            address = None

        city = data.city.strip() if data.city else None
        if city == "":
            city = None

        notes = data.notes.strip() if data.notes else None
        if notes == "":
            notes = None

        discount_percent = data.discount_percent
        if discount_percent is not None:
            if discount_percent < Decimal("0") or discount_percent > Decimal("100"):
                raise CustomerError("Discount percentage must be between 0% and 100%.")

        return CustomerInput(
            name=name,
            phone=phone,
            email=email,
            address=address,
            city=city,
            opening_balance=data.opening_balance,
            credit_limit=data.credit_limit,
            discount_percent=discount_percent,
            notes=notes,
            is_active=data.is_active,
        )
