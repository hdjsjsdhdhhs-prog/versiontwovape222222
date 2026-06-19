from app.db.models import Product


def display_price(product: Product) -> int:
    return product.sale_price if product.is_sale and product.sale_price is not None else product.price


def old_display_price(product: Product) -> int | None:
    price = display_price(product)
    if not product.is_sale or product.old_price is None or product.old_price <= price:
        return None
    return product.old_price


def sale_badge(product: Product) -> str | None:
    if not product.is_sale or not product.sale_badge:
        return None
    return product.sale_badge.strip() or None


def format_price(amount_minor: int, currency: str = "RUB") -> str:
    value = amount_minor / 100
    if currency == "RUB":
        return f"{value:,.0f} ₽".replace(",", " ")
    return f"{value:,.2f} {currency}".replace(",", " ")
