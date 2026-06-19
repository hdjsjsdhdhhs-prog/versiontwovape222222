from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import DeliveryMethod, Order, OrderItem, OrderStatus, OrderStatusHistory, PaymentMethod, ProductFlavor
from app.services.pricing import display_price, format_price
from app.services.telegram import escape_html, send_message

CUSTOMER_PAYMENT_METHODS = {PaymentMethod.CASH, PaymentMethod.CARD}


class OrderError(ValueError):
    pass


class InsufficientStockError(OrderError):
    pass


def normalize_contact_text(value: str | None) -> str:
    contact = (value or "").strip()
    if not contact:
        raise OrderError("contact_required")
    return contact


def calculate_financials(items: list[OrderItem]) -> tuple[int, int, int]:
    revenue = sum((item.unit_sale_price if item.unit_sale_price is not None else item.unit_price) * item.quantity for item in items)
    cost = sum(item.unit_cost_price * item.quantity for item in items)
    return revenue, cost, revenue - cost


def create_order(
    db: Session,
    customer_telegram_username: str,
    cart_items: dict[str, int],
    payment_method: PaymentMethod,
    delivery_method: DeliveryMethod,
    address: str | None,
    comment: str | None,
) -> Order:
    if payment_method not in CUSTOMER_PAYMENT_METHODS:
        raise OrderError("payment_method_invalid")
    customer_telegram_username = normalize_contact_text(customer_telegram_username)
    if delivery_method is DeliveryMethod.COURIER and not (address or "").strip():
        raise OrderError("address_required")

    aggregated: dict[str, int] = defaultdict(int)
    for flavor_id, quantity in cart_items.items():
        aggregated[flavor_id] += quantity
    if not aggregated:
        raise OrderError("empty_cart")

    flavors = db.scalars(
        select(ProductFlavor)
        .where(ProductFlavor.id.in_(aggregated.keys()))
        .options(selectinload(ProductFlavor.product))
        .with_for_update()
    ).all()
    flavor_map = {flavor.id: flavor for flavor in flavors}
    if len(flavor_map) != len(aggregated):
        raise OrderError("flavor_unavailable")

    for flavor_id, quantity in aggregated.items():
        flavor = flavor_map[flavor_id]
        product = flavor.product
        if product is None or not product.is_active:
            raise OrderError("product_unavailable")
        if flavor.stock_quantity < quantity:
            raise InsufficientStockError(f'Not enough stock for "{product.name} - {flavor.name}". Available: {flavor.stock_quantity}, requested: {quantity}.')

    first_flavor = next(iter(flavor_map.values()))
    first_product = first_flavor.product
    order = Order(
        customer_telegram_username=customer_telegram_username,
        payment_method=payment_method,
        delivery_method=delivery_method,
        address=(address or "").strip() or None,
        comment=(comment or "").strip() or None,
        total=0,
        currency=(first_product.currency if first_product else None) or "RUB",
    )
    db.add(order)

    total = 0
    for flavor_id, quantity in aggregated.items():
        flavor = flavor_map[flavor_id]
        product = flavor.product
        unit_price = display_price(product)
        total += unit_price * quantity
        flavor.stock_quantity -= quantity
        order.items.append(
            OrderItem(
                product_id=product.id,
                flavor_id=flavor.id,
                product_name=product.name,
                flavor_name=flavor.name,
                unit_price=unit_price,
                unit_sale_price=unit_price,
                unit_cost_price=product.cost_price,
                quantity=quantity,
            )
        )
    order.total = total
    order.status_history.append(OrderStatusHistory(from_status=None, to_status=OrderStatus.PENDING, changed_by="customer"))
    db.flush()
    notify_new_order(order)
    return order


def change_order_status(db: Session, order: Order, next_status: OrderStatus) -> None:
    current_status = order.status
    if current_status is next_status:
        return

    if next_status is OrderStatus.COMPLETED:
        revenue, cost, profit = calculate_financials(order.items)
        order.revenue = revenue
        order.cost = cost
        order.profit = profit
        order.completed_at = order.completed_at or datetime.now(timezone.utc)
    else:
        order.revenue = 0
        order.cost = 0
        order.profit = 0
        order.completed_at = None

    order.status = next_status
    order.status_history.append(OrderStatusHistory(from_status=current_status, to_status=next_status, changed_by="admin"))
    db.flush()


def get_order_for_admin(db: Session, order_id: str) -> Order | None:
    return db.scalar(select(Order).where(Order.id == order_id).options(selectinload(Order.items)))


def notify_new_order(order: Order) -> None:
    settings = get_settings()
    safe_contact = escape_html(order.customer_telegram_username)
    items = "\n".join(
        f"- {escape_html(item.product_name)} / {escape_html(item.flavor_name)} x {item.quantity} - {format_price((item.unit_sale_price or item.unit_price) * item.quantity, order.currency)}"
        for item in order.items
    )
    admin_text = "\n".join(
        part
        for part in [
            f"<b>New order #{order.id[-6:]}</b>",
            "",
            f"<b>Contact:</b> {safe_contact}",
            f"<b>Payment:</b> {order.payment_method.value}",
            f"<b>Delivery:</b> {order.delivery_method.value}",
            f"<b>Address:</b> {escape_html(order.address)}" if order.address else "",
            f"<b>Comment:</b> {escape_html(order.comment)}" if order.comment else "",
            "",
            "<b>Items:</b>",
            items,
            "",
            f"<b>Total:</b> {format_price(order.total, order.currency)}",
        ]
        if part
    )
    send_message(settings.telegram_bot_token, settings.admin_chat_id, admin_text)
