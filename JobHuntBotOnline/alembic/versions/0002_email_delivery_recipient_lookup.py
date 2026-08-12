"""Keep recipient mail limits after an account is deleted.

The field stores the existing keyed email lookup, not an address or a new
Secret.  It lets delivery-rate audit rows remain useful after their user FK is
set to NULL by account deletion.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0002_delivery_lookup"
down_revision = "0001_saas_baseline"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_email_deliveries_recipient_lookup_created_at"


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("email_deliveries")}
    if "recipient_lookup" not in columns:
        op.add_column("email_deliveries", sa.Column("recipient_lookup", sa.String(length=64), nullable=True))

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE email_deliveries AS delivery
            SET recipient_lookup = users.email_lookup
            FROM users
            WHERE delivery.recipient_lookup IS NULL
              AND delivery.user_id = users.id
            """
        )
    else:
        op.execute(
            """
            UPDATE email_deliveries
            SET recipient_lookup = (
                SELECT users.email_lookup
                FROM users
                WHERE users.id = email_deliveries.user_id
            )
            WHERE recipient_lookup IS NULL
              AND user_id IS NOT NULL
            """
        )

    indexes = {index["name"] for index in inspect(bind).get_indexes("email_deliveries")}
    if INDEX_NAME not in indexes:
        op.create_index(INDEX_NAME, "email_deliveries", ["recipient_lookup", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in inspect(bind).get_indexes("email_deliveries")}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="email_deliveries")
    columns = {column["name"] for column in inspect(bind).get_columns("email_deliveries")}
    if "recipient_lookup" in columns:
        op.drop_column("email_deliveries", "recipient_lookup")
