"""Add audit_logs table."""

from __future__ import annotations

from alembic import op

revision = "0006_audit_logs"
down_revision = "0005_user_password_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            actor_user_id BIGINT NOT NULL,
            action VARCHAR(128) NOT NULL,
            entity_type VARCHAR(64) NULL,
            entity_id VARCHAR(128) NULL,
            ip VARCHAR(64) NULL,
            user_agent VARCHAR(255) NULL,
            meta TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_user_id ON audit_logs(actor_user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs(action);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_type ON audit_logs(entity_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_id ON audit_logs(entity_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE;")



