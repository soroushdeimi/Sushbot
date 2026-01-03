"""Add support_messages table for threaded support conversations."""

from __future__ import annotations

from alembic import op

revision = "0002_support_messages"
down_revision = "0001_user_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_messages (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
            sender_id BIGINT NULL,
            sender_type VARCHAR(16) NOT NULL DEFAULT 'user',
            message_type VARCHAR(16) NOT NULL DEFAULT 'text',
            text TEXT NULL,
            telegram_file_id VARCHAR(255) NULL,
            caption TEXT NULL,
            meta TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_messages_ticket_id ON support_messages(ticket_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_messages_sender_id ON support_messages(sender_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_messages_sender_type ON support_messages(sender_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_messages_message_type ON support_messages(message_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_messages_created_at ON support_messages(created_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS support_messages CASCADE;")



