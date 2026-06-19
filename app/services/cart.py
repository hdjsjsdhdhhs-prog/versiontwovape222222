from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import make_signed_token, read_signed_token
from app.db.models import Product, ProductFlavor
from app.services.pricing import display_price

CART_COOKIE = "shop_cart"


@dataclass(frozen=True)
class CartLine:
    product: Product
    flavor: ProductFlavor
    quantity: int
    line_total: int


@dataclass(frozen=True)
class CartState:
    items: dict[str, int]
    lines: list[CartLine]
    quantity: int
    total: int
    currency: str


def read_cart(token: str | None) -> dict[str, int]:
    payload = read_signed_token(token, "cart")
    raw_items = payload.get("items") if payload else None
    if not isinstance(raw_items, dict):
        return {}
    items: dict[str, int] = {}
    for flavor_id, quantity in raw_items.items():
        if isinstance(flavor_id, str) and isinstance(quantity, int) and quantity > 0:
            items[flavor_id] = min(quantity, 99)
    return items


def write_cart(items: dict[str, int]) -> str:
    cleaned = {flavor_id: max(1, min(99, quantity)) for flavor_id, quantity in items.items() if quantity > 0}
    return make_signed_token({"items": cleaned}, "cart")


def cart_quantity(items: dict[str, int]) -> int:
    return sum(items.values())


def clamp_cart_quantity(quantity: int, stock_quantity: int) -> int:
    if quantity <= 0 or stock_quantity <= 0:
        return 0
    return min(quantity, stock_quantity, 99)


def hydrate_cart(db: Session, items: dict[str, int]) -> list[CartLine]:
    if not items:
        return []
    flavors = db.scalars(
        select(ProductFlavor)
        .where(ProductFlavor.id.in_(items.keys()), ProductFlavor.stock_quantity > 0)
        .options(selectinload(ProductFlavor.product))
        .order_by(ProductFlavor.product_id.asc(), ProductFlavor.created_at.asc())
    ).all()
    lines: list[CartLine] = []
    for flavor in flavors:
        product = flavor.product
        if product is None or not product.is_active:
            continue
        quantity = clamp_cart_quantity(items.get(flavor.id, 0), flavor.stock_quantity)
        if quantity > 0:
            lines.append(CartLine(product=product, flavor=flavor, quantity=quantity, line_total=display_price(product) * quantity))
    return lines


def cart_total(lines: list[CartLine]) -> int:
    return sum(line.line_total for line in lines)


def resolve_cart(db: Session, items: dict[str, int]) -> CartState:
    lines = hydrate_cart(db, items)
    resolved_items = {line.flavor.id: line.quantity for line in lines}
    return CartState(
        items=resolved_items,
        lines=lines,
        quantity=cart_quantity(resolved_items),
        total=cart_total(lines),
        currency=lines[0].product.currency if lines else "RUB",
    )
