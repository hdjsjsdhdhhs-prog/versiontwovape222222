"""remove telegram authentication identity

Revision ID: 202606140001
Revises: 202606100001
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606140001"
down_revision: str | None = "202606100001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("customer_telegram_username", sa.String(length=255), nullable=True))

    op.execute(
        """
        UPDATE orders
        SET customer_telegram_username = COALESCE(
            NULLIF('@' || NULLIF(users.username, ''), '@'),
            '@telegram_' || users.telegram_id,
            '@unknown'
        )
        FROM users
        WHERE orders.user_id = users.id
        """
    )
    op.execute("UPDATE orders SET customer_telegram_username = '@unknown' WHERE customer_telegram_username IS NULL")

    op.alter_column("orders", "customer_telegram_username", nullable=False)
    op.create_index(op.f("ix_orders_customer_telegram_username"), "orders", ["customer_telegram_username"], unique=False)

    op.drop_index(op.f("ix_favorites_user_id"), table_name="favorites")
    op.drop_index(op.f("ix_favorites_product_id"), table_name="favorites")
    op.drop_table("favorites")

    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_constraint("orders_user_id_fkey", "orders", type_="foreignkey")
    op.drop_column("orders", "user_id")

    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")


def downgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("telegram_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("photo_url", sa.String(length=2048), nullable=True),
        sa.Column("language_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)
    op.add_column("orders", sa.Column("user_id", sa.String(length=32), nullable=True))

    op.execute(
        """
        INSERT INTO users (id, telegram_id, username)
        SELECT
            substr(md5(customer_telegram_username), 1, 32),
            substr(md5(customer_telegram_username), 1, 16),
            ltrim(customer_telegram_username, '@')
        FROM orders
        GROUP BY customer_telegram_username
        """
    )
    op.execute(
        """
        UPDATE orders
        SET user_id = users.id
        FROM users
        WHERE users.username = ltrim(orders.customer_telegram_username, '@')
        """
    )
    op.alter_column("orders", "user_id", nullable=False)
    op.create_foreign_key("orders_user_id_fkey", "orders", "users", ["user_id"], ["id"])
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"], unique=False)

    op.create_table(
        "favorites",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("product_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),
    )
    op.create_index(op.f("ix_favorites_product_id"), "favorites", ["product_id"], unique=False)
    op.create_index(op.f("ix_favorites_user_id"), "favorites", ["user_id"], unique=False)

    op.drop_index(op.f("ix_orders_customer_telegram_username"), table_name="orders")
    op.drop_column("orders", "customer_telegram_username")
