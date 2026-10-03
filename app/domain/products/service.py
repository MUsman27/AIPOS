"""Create, update, search, and delete catalog products."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.infrastructure.barcode.normalize import normalize_barcode
from app.infrastructure.database.models import Manufacturer, Product

_MAX_PRICE = Decimal("10000000000")
_TWOPLACES = Decimal("0.01")
logger = logging.getLogger("aipos.products")


class ProductError(Exception):
    """A catalog rule was broken."""


@dataclass(slots=True)
class ProductInput:
    name: str
    unit_price: Decimal | None = None
    sku: str | None = None
    barcode: str | None = None
    cost_price: Decimal | None = None
    is_active: bool = True
    description_ur: str | None = None
    model: str | None = None
    manufacturer_name: str | None = None


_MISSING_NAME_VALUES = {
    "",
    "NA",
    "N/A",
    "N.A",
    "NULL",
    "NONE",
    "UNKNOWN",
}


class ProductService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def translate_missing_names(
        self,
        *,
        translator: Callable[[str], str] | None = None,
    ) -> int:
        """Translate Urdu product descriptions into English for blank or NA names."""
        translator = translator or self._default_urdu_to_english
        products_to_update: list[tuple[Product, str]] = []
        for product in self.session.scalars(select(Product).order_by(Product.id)):
            if not self._is_missing_name(product.name):
                continue
            source = (product.description_ur or product.model or "").strip()
            if source:
                products_to_update.append((product, source))

        logger.info(
            "translate_missing_names: found %s missing-name products to translate",
            len(products_to_update),
        )
        return self._apply_translations(products_to_update, translator)

    def translate_selected_missing_names(
        self,
        product_ids: list[int],
        *,
        translator: Callable[[str], str] | None = None,
        limit: int = 10,
    ) -> int:
        """Translate a selected subset of blank-name products, capped at 10 items."""
        translator = translator or self._default_urdu_to_english
        seen: set[int] = set()
        products_to_update: list[tuple[Product, str]] = []
        for product_id in product_ids[:limit]:
            if product_id in seen:
                continue
            seen.add(product_id)
            product = self.get(product_id)
            if product is None:
                logger.warning("translate_selected_missing_names: product id %s not found", product_id)
                continue
            if not self._is_missing_name(product.name):
                logger.info("translate_selected_missing_names: skipping product %s because name is not missing", product_id)
                continue
            source = (product.description_ur or product.model or "").strip()
            if source:
                products_to_update.append((product, source))
                logger.info("translate_selected_missing_names: queued product %s with source '%s'", product_id, source)
            else:
                logger.warning("translate_selected_missing_names: no Urdu/model source for product %s", product_id)

        logger.info(
            "translate_selected_missing_names: translating %s selected products",
            len(products_to_update),
        )
        return self._apply_translations(products_to_update, translator)

    def _apply_translations(
        self,
        products_to_update: list[tuple[Product, str]],
        translator: Callable[[str], str],
    ) -> int:
        if not products_to_update:
            logger.info("_apply_translations: no products to update")
            return 0

        logger.info("_apply_translations: starting batch translation for %s products", len(products_to_update))
        if translator is self._default_urdu_to_english:
            translations = self._batch_translate_urdu(
                [source for _, source in products_to_update]
            )
        else:
            translations = [translator(source).strip() for _, source in products_to_update]

        updated = 0
        for (product, source), translated in zip(products_to_update, translations):
            cleaned = (translated or "").strip()
            logger.info(
                "_apply_translations: product %s source='%s' translated='%s'",
                product.id,
                source,
                cleaned,
            )
            if cleaned and cleaned != source:
                product.name = cleaned[:500]
                updated += 1
                logger.info("_apply_translations: updated product %s name to '%s'", product.id, cleaned[:500])

        self.session.commit()
        logger.info("_apply_translations: committed %s product updates", updated)
        return updated

    @staticmethod
    def _is_missing_name(value: str | None) -> bool:
        if value is None:
            return True
        cleaned = value.strip()
        return not cleaned or cleaned.upper() in _MISSING_NAME_VALUES

    @staticmethod
    def _default_urdu_to_english(text: str) -> str:
        try:
            from deep_translator import GoogleTranslator
            from deep_translator.exceptions import TooManyRequests
        except ImportError as exc:  # pragma: no cover - dependency is optional at runtime
            raise RuntimeError(
                "Install deep-translator to convert Urdu descriptions into English names."
            ) from exc

        translator = GoogleTranslator(source="ur", target="en")
        for attempt in range(6):
            try:
                translated = translator.translate(text)
                return translated or text
            except TooManyRequests:
                if attempt == 5:
                    raise
                time.sleep(0.5 * (2**attempt))
        return text

    @staticmethod
    def _batch_translate_urdu(texts: list[str]) -> list[str]:
        if not texts:
            return []
        try:
            from deep_translator import GoogleTranslator
            from deep_translator.exceptions import TooManyRequests
        except ImportError as exc:  # pragma: no cover - dependency is optional at runtime
            raise RuntimeError(
                "Install deep-translator to convert Urdu descriptions into English names."
            ) from exc

        translator = GoogleTranslator(source="ur", target="en")
        translated: list[str] = []
        batch_size = 3
        for index in range(0, len(texts), batch_size):
            chunk = texts[index : index + batch_size]
            for attempt in range(6):
                try:
                    if hasattr(translator, "translate_batch"):
                        batch_result = translator.translate_batch(chunk)
                        translated.extend(batch_result or [])
                    else:
                        translated.extend(
                            translator.translate(item) or item for item in chunk
                        )
                    break
                except TooManyRequests:
                    if attempt == 5:
                        raise RuntimeError(
                            "Google Translate is rate-limited right now. Wait 30-60 seconds, then try again in a smaller batch."
                        ) from None
                    time.sleep(1.0 * (2**attempt))
            time.sleep(0.75)

        return translated[: len(texts)]

    def search(self, text: str | None = None) -> list[Product]:
        statement = (
            select(Product)
            .options(selectinload(Product.manufacturer))
            .order_by(Product.name, Product.id)
        )
        cleaned = (text or "").strip()
        if cleaned:
            pattern = f"%{cleaned}%"
            statement = statement.where(
                or_(
                    Product.name.ilike(pattern),
                    Product.description_ur.ilike(pattern),
                    Product.sku.ilike(pattern),
                    Product.barcode.ilike(pattern),
                    Product.model.ilike(pattern),
                    Product.manufacturer.has(Manufacturer.name.ilike(pattern)),
                )
            )
        return list(self.session.scalars(statement))

    def list_manufacturers(self) -> list[Manufacturer]:
        statement = select(Manufacturer).order_by(Manufacturer.name, Manufacturer.id)
        return list(self.session.scalars(statement))

    def get(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def get_by_barcode(self, code: str | None) -> Product | None:
        barcode = normalize_barcode(code)
        if barcode is None:
            return None
        return self.session.scalar(select(Product).where(Product.barcode == barcode))

    def create(self, data: ProductInput) -> Product:
        fields = self._normalize(data)
        try:
            manufacturer = self._ensure_manufacturer(fields.manufacturer_name)
            manufacturer_id = manufacturer.id if manufacturer is not None else None
            self._ensure_unique(fields.sku, fields.barcode, manufacturer_id)
            product = Product(
                name=fields.name or None,
                sku=fields.sku,
                barcode=fields.barcode,
                description_ur=fields.description_ur,
                model=fields.model,
                unit_price=fields.unit_price,
                cost_price=fields.cost_price,
                is_active=fields.is_active,
                manufacturer=manufacturer,
            )
            self.session.add(product)
            self._commit()
            self.session.refresh(product)
            return product
        except Exception:
            self.session.rollback()
            raise

    def update(self, product_id: int, data: ProductInput) -> Product:
        product = self.session.get(Product, product_id)
        if product is None:
            raise ProductError("Product not found.")
        fields = self._normalize(data)
        try:
            manufacturer = self._ensure_manufacturer(fields.manufacturer_name)
            manufacturer_id = manufacturer.id if manufacturer is not None else None
            self._ensure_unique(
                fields.sku,
                fields.barcode,
                manufacturer_id,
                exclude_id=product_id,
            )
            product.name = fields.name or None
            product.sku = fields.sku
            product.barcode = fields.barcode
            product.description_ur = fields.description_ur
            product.model = fields.model
            product.unit_price = fields.unit_price
            product.cost_price = fields.cost_price
            product.is_active = fields.is_active
            product.manufacturer = manufacturer
            self._commit()
            self.session.refresh(product)
            return product
        except Exception:
            self.session.rollback()
            raise

    def update_sale_prices(
        self,
        updates: list[tuple[int, Decimal | None]],
    ) -> int:
        """Batch update unit_price (sale price) for specified product IDs."""
        if not updates:
            return 0
        updated_count = 0
        try:
            for product_id, sale_price in updates:
                product = self.session.get(Product, product_id)
                if product is None:
                    continue
                cleaned_price = self._optional_price(sale_price, "Sale price")
                if product.unit_price != cleaned_price:
                    product.unit_price = cleaned_price
                    updated_count += 1
            self._commit()
            return updated_count
        except Exception:
            self.session.rollback()
            raise

    def delete(self, product_id: int) -> None:
        product = self.session.get(Product, product_id)
        if product is None:
            raise ProductError("Product not found.")
        self.session.delete(product)
        self._commit()

    def _normalize(self, data: ProductInput) -> ProductInput:
        name = data.name.strip()
        if len(name) > 500:
            raise ProductError("English description must be 500 characters or fewer.")
        description_ur = self._clean_text(
            data.description_ur, limit=500, label="Urdu description"
        )
        if not name and not description_ur:
            raise ProductError("English description is required.")
        return ProductInput(
            name=name,
            sku=self._clean_code(data.sku, limit=64, label="SKU"),
            barcode=self._clean_barcode(data.barcode),
            unit_price=self._optional_price(data.unit_price, "Sale price"),
            cost_price=self._optional_price(data.cost_price, "Purchase price"),
            is_active=bool(data.is_active),
            description_ur=description_ur,
            model=self._clean_text(data.model, limit=120, label="Model"),
            manufacturer_name=self._clean_text(
                data.manufacturer_name, limit=200, label="Manufacturer"
            ),
        )

    def _clean_text(self, value: str | None, *, limit: int, label: str) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            return None
        if len(cleaned) > limit:
            raise ProductError(f"{label} must be {limit} characters or fewer.")
        return cleaned

    def _clean_code(self, value: str | None, *, limit: int, label: str) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > limit:
            raise ProductError(f"{label} must be {limit} characters or fewer.")
        return cleaned

    def _clean_barcode(self, value: str | None) -> str | None:
        cleaned = normalize_barcode(value)
        if cleaned is not None and len(cleaned) > 64:
            raise ProductError("Barcode must be 64 characters or fewer.")
        return cleaned

    def _optional_price(self, value: Decimal | None, label: str) -> Decimal | None:
        return self._clean_price(value, required=False, label=label)

    def _clean_price(
        self, value: Decimal | None, *, required: bool, label: str
    ) -> Decimal | None:
        if value is None:
            if required:
                raise ProductError(f"{label} is required.")
            return None
        if not isinstance(value, Decimal):
            raise ProductError(f"{label} must be a decimal amount.")
        if value < 0:
            raise ProductError(f"{label} must be zero or greater.")
        if value >= _MAX_PRICE:
            raise ProductError(f"{label} is too large.")
        return value.quantize(_TWOPLACES)

    def _ensure_manufacturer(self, name: str | None) -> Manufacturer | None:
        if name is None:
            return None
        existing = self.session.scalar(
            select(Manufacturer).where(Manufacturer.name == name)
        )
        if existing is not None:
            return existing
        manufacturer = Manufacturer(name=name)
        self.session.add(manufacturer)
        self.session.flush()
        return manufacturer

    def _ensure_unique(
        self,
        sku: str | None,
        barcode: str | None,
        manufacturer_id: int | None,
        exclude_id: int | None = None,
    ) -> None:
        if sku is not None:
            statement = select(Product).where(Product.sku == sku)
            if manufacturer_id is None:
                statement = statement.where(Product.manufacturer_id.is_(None))
            else:
                statement = statement.where(Product.manufacturer_id == manufacturer_id)
            existing = self.session.scalar(statement)
            if existing is not None and existing.id != exclude_id:
                raise ProductError(f"SKU {sku} is already used.")
        if barcode is not None:
            existing = self.session.scalar(
                select(Product).where(Product.barcode == barcode)
            )
            if existing is not None and existing.id != exclude_id:
                raise ProductError(f"Barcode {barcode} is already used.")

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ProductError("SKU or barcode is already used.") from None
