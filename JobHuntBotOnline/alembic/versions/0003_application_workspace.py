"""Add editable application state while preserving an immutable revision trail."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0003_application_workspace"
down_revision = "0002_delivery_lookup"
branch_labels = None
depends_on = None

PROGRESS_TABLE = "application_progresses"
PROGRESS_INDEXES = {
    "ix_application_progresses_user_id": ["user_id"],
    "ix_application_progresses_job_id": ["job_id"],
    "ix_application_progresses_status": ["status"],
    "ix_application_progresses_updated_at": ["updated_at"],
}


def _columns(bind, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if PROGRESS_TABLE not in tables:
        op.create_table(
            PROGRESS_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("evidence_encrypted", sa.LargeBinary(), nullable=True),
            sa.Column("notes_encrypted", sa.LargeBinary(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("user_id", "job_id", name="uq_application_progresses_user_job"),
        )

    indexes = {index["name"] for index in inspect(bind).get_indexes(PROGRESS_TABLE)}
    for name, columns in PROGRESS_INDEXES.items():
        if name not in indexes:
            op.create_index(name, PROGRESS_TABLE, columns, unique=False)

    pack_columns = _columns(bind, "application_packs")
    if "updated_at" not in pack_columns:
        op.add_column(
            "application_packs",
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if "version" not in pack_columns:
        op.add_column("application_packs", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.execute("UPDATE application_packs SET updated_at = created_at WHERE updated_at IS NULL")

    event_columns = _columns(bind, "application_events")
    if "action" not in event_columns:
        op.add_column("application_events", sa.Column("action", sa.String(length=24), nullable=False, server_default="recorded"))
    if "revision" not in event_columns:
        op.add_column("application_events", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))

    # Existing records were append-only.  Preserve every old event and create
    # one editable current state from the latest event per user/job.
    op.execute(
        """
        INSERT INTO application_progresses (
            user_id, job_id, status, evidence_encrypted, notes_encrypted,
            created_at, updated_at, version
        )
        SELECT event.user_id, event.job_id, event.status,
               event.evidence_encrypted, event.notes_encrypted,
               event.created_at, event.created_at, 1
        FROM application_events AS event
        WHERE NOT EXISTS (
            SELECT 1
            FROM application_progresses AS progress
            WHERE progress.user_id = event.user_id
              AND progress.job_id = event.job_id
        )
          AND NOT EXISTS (
            SELECT 1
            FROM application_events AS newer
            WHERE newer.user_id = event.user_id
              AND newer.job_id = event.job_id
              AND (
                  newer.created_at > event.created_at
                  OR (newer.created_at = event.created_at AND newer.id > event.id)
              )
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if PROGRESS_TABLE in tables:
        indexes = {index["name"] for index in inspect(bind).get_indexes(PROGRESS_TABLE)}
        for name in PROGRESS_INDEXES:
            if name in indexes:
                op.drop_index(name, table_name=PROGRESS_TABLE)
        op.drop_table(PROGRESS_TABLE)

    event_columns = _columns(bind, "application_events")
    if "revision" in event_columns:
        op.drop_column("application_events", "revision")
    if "action" in event_columns:
        op.drop_column("application_events", "action")

    pack_columns = _columns(bind, "application_packs")
    if "version" in pack_columns:
        op.drop_column("application_packs", "version")
    if "updated_at" in pack_columns:
        op.drop_column("application_packs", "updated_at")
