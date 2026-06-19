from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Order, OrderStatus
from app.services.orders import calculate_financials

MOSCOW = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class DateRange:
    from_date: date | None
    to_date: date | None
    start: datetime | None
    end: datetime | None


def moscow_today() -> date:
    return datetime.now(MOSCOW).date()


def make_range(from_date: date, to_date: date) -> DateRange:
    start_date, end_date = sorted([from_date, to_date])
    start = datetime.combine(start_date, time.min, tzinfo=MOSCOW)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=MOSCOW)
    return DateRange(start_date, end_date, start, end)


def all_time_range() -> DateRange:
    return DateRange(None, None, None, None)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def presets() -> dict[str, DateRange]:
    today = moscow_today()
    return {
        "today": make_range(today, today),
        "yesterday": make_range(today - timedelta(days=1), today - timedelta(days=1)),
        "week": make_range(today - timedelta(days=6), today),
        "month": make_range(today.replace(day=1), today),
        "allTime": all_time_range(),
    }


def load_completed_orders(db: Session) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .where(Order.status == OrderStatus.COMPLETED)
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc())
        )
    )


def in_range(order: Order, date_range: DateRange) -> bool:
    value = order.completed_at or order.created_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    if date_range.start and value < date_range.start:
        return False
    if date_range.end and value >= date_range.end:
        return False
    return True


def summarize(orders: list[Order], date_range: DateRange) -> dict[str, object]:
    filtered = [order for order in orders if in_range(order, date_range)]
    revenue = cost = profit = 0
    for order in filtered:
        order_revenue, order_cost, order_profit = calculate_financials(order.items)
        revenue += order_revenue
        cost += order_cost
        profit += order_profit
    return {
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "order_count": len(filtered),
        "currency": filtered[0].currency if filtered else "RUB",
        "from_date": date_range.from_date,
        "to_date": date_range.to_date,
    }
