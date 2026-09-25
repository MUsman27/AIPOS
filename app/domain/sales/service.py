"""Sale service for processing point of sale transactions and order history."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.infrastructure.database.models import Customer, Product, Sale, SaleItem


class SaleError(Exception):
    """Domain error raised during sale operations."""


@dataclass
class SaleItemInput:
    """Input payload for a single sale line item."""

    product_name: str
    unit_price: Decimal
    quantity: Decimal = Decimal("1.00")
    discount_amount: Decimal = Decimal("0.00")
    product_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    cost_price: Decimal | None = None
    line_total: Decimal | None = None


@dataclass
class SaleInput:
    """Input payload for completing a sale."""

    items: list[SaleItemInput] = field(default_factory=list)
    customer_id: int | None = None
    discount_amount: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    paid_amount: Decimal = Decimal("0.00")
    payment_method: str = "Cash"
    notes: str | None = None
    sale_date: datetime | None = None


class SaleService:
    """Business logic for sales transactions, invoices, and customer balance updates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def generate_invoice_number(self) -> str:
        """Generate a unique sequential invoice number (e.g. INV-20260924-0001)."""
        date_str = datetime.now().strftime("%Y%m%d")
        prefix = f"INV-{date_str}-"

        stmt = (
            select(Sale.invoice_number)
            .where(Sale.invoice_number.like(f"{prefix}%"))
            .order_by(Sale.id.desc())
            .limit(1)
        )
        last_invoice = self._session.scalar(stmt)

        if not last_invoice:
            seq = 1
        else:
            try:
                seq = int(last_invoice.split("-")[-1]) + 1
            except ValueError:
                seq = 1

        return f"{prefix}{seq:04d}"

    def get_sale(self, sale_id: int) -> Sale | None:
        """Fetch sale by primary key with preloaded items and customer."""
        stmt = (
            select(Sale)
            .options(joinedload(Sale.items), joinedload(Sale.customer))
            .where(Sale.id == sale_id)
        )
        return self._session.scalar(stmt)

    def get_by_invoice(self, invoice_number: str) -> Sale | None:
        """Fetch sale by invoice number."""
        cleaned = invoice_number.strip()
        if not cleaned:
            return None
        stmt = (
            select(Sale)
            .options(joinedload(Sale.items), joinedload(Sale.customer))
            .where(Sale.invoice_number == cleaned)
        )
        return self._session.scalar(stmt)

    def search_sales(
        self,
        query: str = "",
        customer_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[Sale]:
        """Filter sales history by search term, customer, or date range."""
        stmt = select(Sale).options(joinedload(Sale.customer)).order_by(Sale.sale_date.desc(), Sale.id.desc())

        if customer_id is not None:
            stmt = stmt.where(Sale.customer_id == customer_id)

        if start_date is not None:
            stmt = stmt.where(Sale.sale_date >= start_date)

        if end_date is not None:
            stmt = stmt.where(Sale.sale_date <= end_date)

        cleaned = query.strip()
        if cleaned:
            pattern = f"%{cleaned}%"
            stmt = stmt.join(Sale.customer, isouter=True).where(
                or_(
                    Sale.invoice_number.ilike(pattern),
                    Sale.payment_method.ilike(pattern),
                    Sale.payment_status.ilike(pattern),
                    Customer.name.ilike(pattern),
                    Customer.phone.ilike(pattern),
                )
            )

        return list(self._session.scalars(stmt).unique().all())

    def create_sale(self, data: SaleInput) -> Sale:
        """Process and complete a point of sale transaction."""
        if not data.items:
            raise SaleError("Cannot complete a sale with no items.")

        customer = None
        if data.customer_id is not None:
            customer = self._session.get(Customer, data.customer_id)
            if customer is None:
                raise SaleError(f"Customer with ID {data.customer_id} not found.")

        # Process line items and calculate subtotal
        subtotal = Decimal("0.00")
        processed_items: list[SaleItem] = []

        for idx, item in enumerate(data.items, start=1):
            if not item.product_name or not item.product_name.strip():
                raise SaleError(f"Item #{idx} is missing a product name.")
            if item.unit_price < Decimal("0.00"):
                raise SaleError(f"Item '{item.product_name}' has an invalid negative unit price.")
            if item.quantity <= Decimal("0.00"):
                raise SaleError(f"Item '{item.product_name}' must have a quantity greater than 0.")

            line_gross = (item.unit_price * item.quantity).quantize(Decimal("0.01"))
            line_disc = (item.discount_amount or Decimal("0.00")).quantize(Decimal("0.01"))
            line_total = line_gross - line_disc
            if line_total < Decimal("0.00"):
                line_total = Decimal("0.00")

            subtotal += line_total

            sale_item = SaleItem(
                product_id=item.product_id,
                product_name=item.product_name.strip(),
                sku=item.sku.strip() if item.sku else None,
                barcode=item.barcode.strip() if item.barcode else None,
                unit_price=item.unit_price.quantize(Decimal("0.01")),
                cost_price=item.cost_price.quantize(Decimal("0.01")) if item.cost_price is not None else None,
                quantity=item.quantity.quantize(Decimal("0.01")),
                discount_amount=line_disc,
                line_total=line_total,
            )
            processed_items.append(sale_item)

        overall_discount = (data.discount_amount or Decimal("0.00")).quantize(Decimal("0.01"))
        tax_amount = (data.tax_amount or Decimal("0.00")).quantize(Decimal("0.01"))

        total_amount = subtotal - overall_discount + tax_amount
        if total_amount < Decimal("0.00"):
            total_amount = Decimal("0.00")

        paid_amount = (data.paid_amount or Decimal("0.00")).quantize(Decimal("0.01"))

        if paid_amount > total_amount:
            change_amount = paid_amount - total_amount
            payment_status = "Paid"
        elif paid_amount == total_amount:
            change_amount = Decimal("0.00")
            payment_status = "Paid"
        elif paid_amount > Decimal("0.00"):
            change_amount = Decimal("0.00")
            payment_status = "Partial"
        else:
            change_amount = Decimal("0.00")
            payment_status = "Unpaid" if total_amount > Decimal("0.00") else "Paid"

        # Update customer balance if on credit or unpaid portion exists
        unpaid_balance = total_amount - paid_amount
        if unpaid_balance > Decimal("0.00") and customer is not None:
            customer.opening_balance = (customer.opening_balance or Decimal("0.00")) + unpaid_balance

        invoice_no = self.generate_invoice_number()

        sale = Sale(
            invoice_number=invoice_no,
            customer_id=customer.id if customer else None,
            sale_date=data.sale_date or datetime.now(),
            subtotal=subtotal,
            discount_amount=overall_discount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            paid_amount=paid_amount,
            change_amount=change_amount,
            payment_method=data.payment_method or "Cash",
            payment_status=payment_status,
            notes=data.notes.strip() if data.notes else None,
            items=processed_items,
        )

        self._session.add(sale)
        self._session.commit()
        self._session.refresh(sale)
        return sale

    def void_sale(self, sale_id: int) -> bool:
        """Void / Cancel a sale and adjust customer balance if needed."""
        sale = self.get_sale(sale_id)
        if sale is None:
            return False

        # Revert customer balance if unpaid balance was added
        unpaid = sale.total_amount - sale.paid_amount
        if unpaid > Decimal("0.00") and sale.customer is not None:
            sale.customer.opening_balance = (sale.customer.opening_balance or Decimal("0.00")) - unpaid
            if sale.customer.opening_balance < Decimal("0.00"):
                sale.customer.opening_balance = Decimal("0.00")

        self._session.delete(sale)
        self._session.commit()
        return True

    def get_summary_stats(self) -> dict[str, str]:
        """Compute key aggregate metrics for sales reporting."""
        sales = list(self._session.scalars(select(Sale)).all())
        total_count = len(sales)
        total_revenue = sum((s.total_amount for s in sales), Decimal("0.00"))
        total_paid = sum((s.paid_amount for s in sales), Decimal("0.00"))
        total_unpaid = sum((max(Decimal("0.00"), s.total_amount - s.paid_amount) for s in sales), Decimal("0.00"))

        return {
            "total_count": str(total_count),
            "total_revenue": f"${total_revenue:,.2f}",
            "total_paid": f"${total_paid:,.2f}",
            "total_unpaid": f"${total_unpaid:,.2f}",
        }
