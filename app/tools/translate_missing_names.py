"""Backfill name values from Urdu descriptions for products whose English name is blank."""

from app.domain.products.service import ProductService
from app.infrastructure.database.session import get_session


def main() -> None:
    session = get_session()
    service = ProductService(session)
    updated = service.translate_missing_names()
    print(f"Updated {updated} products with translated English names.")


if __name__ == "__main__":
    main()
